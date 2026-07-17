import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.config import logger
from ..services.realtime_service import RealtimeSTTSession
from ..services.speaker_id_service import LiveSpeakerIdentifier
from ..services.meeting_store import MeetingRecord
from ..services.refine_service import refine_meeting

router = APIRouter()


async def _finalize_abnormal(session, recorder, app_state, session_id: str, cause: str) -> None:
    """
    비정상 종료(end 신호 없는 끊김/에러) 공통 처리.
    끊김이 감지되는 경로가 두 갈래(receive의 disconnect 메시지 / send 중 WebSocketDisconnect
    예외)라서, 어느 쪽이든 동일하게 잔여 버퍼 처리 → 회의록 확정 → 재분석 예약이 되게 묶음.
    """
    try:
        # 클라이언트에 보낼 순 없지만, 회의록에는 마지막 발언까지 남긴다
        await session.flush_remaining()
    except Exception:
        logger.exception(f"⚠️ [{session_id}] 종료 시 잔여 버퍼 처리 실패 — 기존 기록까지만 저장됨")
    recorder.finalize("disconnected")
    if recorder.has_content:
        asyncio.create_task(refine_meeting(recorder.meeting_id, app_state))
    logger.info(f"⚪ 실시간 STT 세션 종료({cause}): {session_id}")


@router.websocket("/ws/stt/{session_id}")
async def realtime_stt_ws(websocket: WebSocket, session_id: str, attendees: str = None):
    """
    실시간 회의용 STT 엔드포인트.
    - 프론트는 PCM16LE(16kHz, mono) 오디오를 바이너리 프레임으로 스트리밍
    - 서버는 VAD로 발화가 끊길 때마다 partial(잠정)/final(확정) 결과를 push
    - 확정 결과는 서버에도 저장됨 (오디오 원본 + transcript.json → /api/meetings로 조회)
    - 회의를 끝낼 땐 텍스트 프레임 "end"를 보내면, 잔여 버퍼를 마지막 청크로
      처리한 결과와 "session_end" 메시지를 받은 뒤 정상 종료된다

    화자 프로필 우선순위:
    1. 세션 등록 (/api/enroll — 이번 회의 한정, 게스트 포함 시 사용)
    2. 전역 프로필 (attendees 쿼리 파라미터 — "이준오,가동현"처럼 콤마 구분.
       최초 1회 등록해둔 목소리로 매 회의 재등록 없이 시작하는 방식)
    3. 둘 다 없으면 자동감지(열린 집합) 폴백
    """
    await websocket.accept()

    fast_model = websocket.app.state.stt_model_fast
    precise_model = websocket.app.state.stt_model

    # 1순위: /api/enroll로 이번 회의용으로 등록해둔 프로필.
    # pop이 아니라 get인 이유: 네트워크 문제로 연결이 끊겨 같은 session_id로
    # 재접속할 때 등록 정보가 사라져 있으면 조용히 자동감지 모드로 떨어져버림.
    # 등록 정보 삭제는 명시적 종료(end) 시점 또는 DELETE /api/enroll에서만 수행.
    initial_profiles = websocket.app.state.enrolled_profiles.get(session_id)
    mode = "세션 등록(닫힌 집합)"

    # 2순위: 전역 프로필에서 참석자 선택 — 인원이 확정되므로 닫힌 집합 유지
    if not initial_profiles and attendees:
        names = [n.strip() for n in attendees.split(",") if n.strip()]
        initial_profiles = websocket.app.state.voice_profiles.load(names)
        missing = set(names) - set(initial_profiles.keys())
        if missing:
            logger.warning(f"⚠️ [{session_id}] 전역 프로필 미등록 참석자 무시됨: {', '.join(missing)}")
        if not initial_profiles:
            initial_profiles = None
        mode = f"전역 프로필(닫힌 집합, {len(initial_profiles or {})}명)"

    if not initial_profiles:
        mode = "자동감지(열린 집합)"

    speaker_identifier = LiveSpeakerIdentifier(
        websocket.app.state.speaker_embedding_inference,
        initial_profiles=initial_profiles,
    )
    recorder = MeetingRecord(session_id, "enrolled" if initial_profiles else "auto")
    if initial_profiles:
        # 회의 후 정밀 재분석(C-4)이 익명 화자 라벨을 실제 이름으로 매핑할 때 필요
        recorder.save_profiles(initial_profiles)
    session = RealtimeSTTSession(session_id, fast_model, precise_model, speaker_identifier, recorder)

    logger.info(f"🔴 실시간 STT 세션 시작: {session_id} (화자식별 모드: {mode}, 회의ID: {recorder.meeting_id})")

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "연결 끊김")
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
                    if recorder.has_content:
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
        # 결과 전송(send) 도중 클라이언트가 끊긴 경우 — receive 경로와 동일하게 처리
        await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "전송 중 끊김")
        return
    except Exception:
        logger.exception(f"❌ 실시간 STT 세션 에러 [{session_id}]")
        await _finalize_abnormal(session, recorder, websocket.app.state, session_id, "에러")

    try:
        await websocket.close()
    except Exception:
        pass  # 이미 닫힌 소켓이면 무시
