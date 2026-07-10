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
    # 임베딩 모델(무거움)은 앱 전역에서 공유, 화자 프로필은 이 회의(세션)만의 것으로 새로 생성
    speaker_identifier = LiveSpeakerIdentifier(websocket.app.state.speaker_embedding_inference)
    session = RealtimeSTTSession(session_id, fast_model, precise_model, speaker_identifier)

    logger.info(f"🔴 실시간 STT 세션 시작: {session_id}")

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
