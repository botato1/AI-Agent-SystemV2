from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.config import logger
from ..services.realtime_service import RealtimeSTTSession
from ..services.speaker_id_service import LiveSpeakerIdentifier

router = APIRouter()


@router.websocket("/ws/stt/{session_id}")
async def realtime_stt_ws(websocket: WebSocket, session_id: str):
    """
    실시간 회의용 STT 엔드포인트.
    프론트는 PCM16LE(16kHz, mono) 오디오를 바이너리 프레임으로 이 소켓에 스트리밍하고,
    서버는 VAD로 발화 구간이 끊길 때마다 자동으로 Fast+Precise 2-pass 전사 결과를 돌려준다.
    """
    await websocket.accept()

    fast_model = websocket.app.state.stt_model_fast
    precise_model = websocket.app.state.stt_model

    # /api/enroll로 회의 시작 전 미리 등록해둔 화자 프로필이 있으면 이어받음
    # (있으면 "인원수 고정" 닫힌 집합 모드, 없으면 기존 열린 집합 방식으로 자동 폴백)
    initial_profiles = websocket.app.state.enrolled_profiles.pop(session_id, None)
    speaker_identifier = LiveSpeakerIdentifier(
        websocket.app.state.speaker_embedding_inference,
        initial_profiles=initial_profiles,
    )
    session = RealtimeSTTSession(session_id, fast_model, precise_model, speaker_identifier)

    mode = "사전등록(닫힌 집합)" if initial_profiles else "자동감지(열린 집합)"
    logger.info(f"🔴 실시간 STT 세션 시작: {session_id} (화자식별 모드: {mode})")

    try:
        while True:
            data = await websocket.receive_bytes()
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
    except Exception as e:
        logger.error(f"❌ 실시간 STT 세션 에러 [{session_id}]: {e}")
        await websocket.close(code=1011)
