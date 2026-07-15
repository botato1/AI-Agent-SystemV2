from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.config import logger
from ..services.realtime_service import RealtimeSTTSession
from ..services.speaker_id_service import LiveSpeakerIdentifier

router = APIRouter()


@router.websocket("/ws/stt/{session_id}")
async def realtime_stt_ws(websocket: WebSocket, session_id: str):
    """
    실시간 회의용 STT 엔드포인트.
    - 프론트는 PCM16LE(16kHz, mono) 오디오를 바이너리 프레임으로 스트리밍
    - 서버는 VAD로 발화가 끊길 때마다 partial(잠정)/final(확정) 결과를 push
    - 회의를 끝낼 땐 텍스트 프레임 "end"를 보내면, 잔여 버퍼를 마지막 청크로
      처리한 결과와 "session_end" 메시지를 받은 뒤 정상 종료된다
      (그냥 연결을 끊으면 마지막 발언이 유실될 수 있음)
    """
    await websocket.accept()

    fast_model = websocket.app.state.stt_model_fast
    precise_model = websocket.app.state.stt_model

    # /api/enroll로 회의 시작 전 미리 등록해둔 화자 프로필이 있으면 이어받음.
    # pop이 아니라 get인 이유: 네트워크 문제로 연결이 끊겨 같은 session_id로
    # 재접속할 때 등록 정보가 사라져 있으면 조용히 자동감지 모드로 떨어져버림.
    # 등록 정보 삭제는 명시적 종료(end) 시점 또는 DELETE /api/enroll에서만 수행.
    initial_profiles = websocket.app.state.enrolled_profiles.get(session_id)
    speaker_identifier = LiveSpeakerIdentifier(
        websocket.app.state.speaker_embedding_inference,
        initial_profiles=initial_profiles,
    )
    session = RealtimeSTTSession(session_id, fast_model, precise_model, speaker_identifier)

    mode = "사전등록(닫힌 집합)" if initial_profiles else "자동감지(열린 집합)"
    logger.info(f"🔴 실시간 STT 세션 시작: {session_id} (화자식별 모드: {mode})")

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                # 명시적 end 없이 끊긴 경우 — 잔여 버퍼는 처리해도 보낼 곳이 없으므로
                # 유실량만 로그로 남긴다 (회의록 서버 저장이 붙으면 여기서 저장 처리)
                lost_sec = session._buffer_duration_sec()
                if lost_sec >= 1.0:
                    logger.warning(f"⚠️ [{session_id}] 종료 신호 없이 연결 끊김 — 잔여 버퍼 {lost_sec:.1f}초 유실")
                logger.info(f"⚪ 실시간 STT 세션 종료: {session_id}")
                return

            if message.get("text") is not None:
                if message["text"] == "end":
                    result = await session.flush_remaining()
                    if result:
                        await websocket.send_json(result)
                    await websocket.send_json({"session_id": session_id, "type": "session_end"})
                    # 회의가 정상 종료됐으므로 이 세션의 사전 등록 정보도 정리
                    websocket.app.state.enrolled_profiles.pop(session_id, None)
                    logger.info(f"⚪ 실시간 STT 세션 정상 종료(end): {session_id}")
                    break
                continue  # end 외의 텍스트 프레임은 무시

            data = message.get("bytes")
            if not data:
                continue
            session.push_audio(data)

            # 청크가 끝나기 전에도 1초 주기로 잠정 텍스트를 흘려보냄 (Local Agreement)
            partial = await session.maybe_stream_partial()
            if partial:
                await websocket.send_json(partial)

            if session.should_flush():
                chunk, offset_sec = session.pop_chunk()
                result = await session.process_chunk(chunk, offset_sec)
                await websocket.send_json(result)

    except WebSocketDisconnect:
        logger.info(f"⚪ 실시간 STT 세션 종료: {session_id}")
        return
    except Exception:
        logger.exception(f"❌ 실시간 STT 세션 에러 [{session_id}]")

    try:
        await websocket.close()
    except Exception:
        pass  # 이미 닫힌 소켓이면 무시
