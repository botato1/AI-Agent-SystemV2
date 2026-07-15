import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.config import logger
from ..services.realtime_service import RealtimeSTTSession
from ..services.speaker_id_service import LiveSpeakerIdentifier
from ..services.meeting_store import MeetingRecord
from ..services.refine_service import refine_meeting

router = APIRouter()


@router.websocket("/ws/stt/{session_id}")
async def realtime_stt_ws(websocket: WebSocket, session_id: str):
    """
    실시간 회의용 STT 엔드포인트.
    - 프론트는 PCM16LE(16kHz, mono) 오디오를 바이너리 프레임으로 스트리밍
    - 서버는 VAD로 발화가 끊길 때마다 partial(잠정)/final(확정) 결과를 push
    - 확정 결과는 서버에도 저장됨 (오디오 원본 + transcript.json → /api/meetings로 조회)
    - 회의를 끝낼 땐 텍스트 프레임 "end"를 보내면, 잔여 버퍼를 마지막 청크로
      처리한 결과와 "session_end" 메시지를 받은 뒤 정상 종료된다
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
    recorder = MeetingRecord(session_id, "enrolled" if initial_profiles else "auto")
    if initial_profiles:
        # 회의 후 정밀 재분석(C-4)이 익명 화자 라벨을 실제 이름으로 매핑할 때 필요
        recorder.save_profiles(initial_profiles)
    session = RealtimeSTTSession(session_id, fast_model, precise_model, speaker_identifier, recorder)

    mode = "사전등록(닫힌 집합)" if initial_profiles else "자동감지(열린 집합)"
    logger.info(f"🔴 실시간 STT 세션 시작: {session_id} (화자식별 모드: {mode}, 회의ID: {recorder.meeting_id})")

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                # 명시적 end 없이 끊긴 경우 — 클라이언트에 보낼 순 없지만,
                # 잔여 버퍼를 처리해서 회의록에는 마지막 발언까지 남긴다
                await session.flush_remaining()
                recorder.finalize("disconnected")
                # 끊긴 회의도 저장된 부분까지는 정밀 재분석 (백그라운드)
                asyncio.create_task(refine_meeting(recorder.meeting_id, websocket.app.state))
                logger.info(f"⚪ 실시간 STT 세션 종료(연결 끊김): {session_id}")
                return

            if message.get("text") is not None:
                if message["text"] == "end":
                    result = await session.flush_remaining()
                    if result:
                        await websocket.send_json(result)
                    recorder.finalize("completed")
                    await websocket.send_json({
                        "session_id": session_id,
                        "type": "session_end",
                        "meeting_id": recorder.meeting_id,
                    })
                    # 회의가 정상 종료됐으므로 이 세션의 사전 등록 정보도 정리
                    websocket.app.state.enrolled_profiles.pop(session_id, None)
                    # 회의 후 정밀 재분석(C-4) 백그라운드 실행 — 화자 오배정/청크 경계 오류 보정
                    asyncio.create_task(refine_meeting(recorder.meeting_id, websocket.app.state))
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
        recorder.finalize("disconnected")
        logger.info(f"⚪ 실시간 STT 세션 종료: {session_id}")
        return
    except Exception:
        recorder.finalize("disconnected")
        logger.exception(f"❌ 실시간 STT 세션 에러 [{session_id}]")

    try:
        await websocket.close()
    except Exception:
        pass  # 이미 닫힌 소켓이면 무시
