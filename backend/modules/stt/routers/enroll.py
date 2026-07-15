import numpy as np
from fastapi import APIRouter, Request

from ..core.config import logger, REALTIME_SAMPLE_RATE
from ..services.speaker_id_service import LiveSpeakerIdentifier

router = APIRouter()


@router.post("/enroll/{session_id}")
async def enroll_speaker(session_id: str, speaker_name: str, request: Request):
    """
    회의 시작 전, 참석자 한 명이 몇 초간 말한 PCM16LE(16kHz, mono) 오디오를
    요청 바디로 받아 화자 임베딩("목소리 지문")을 미리 등록해둔다.

    같은 session_id로 여러 명을 순서대로 등록할 수 있고, 이후 실시간
    WebSocket(/api/ws/stt/{session_id})이 같은 session_id로 연결되면
    이 등록 정보를 그대로 이어받아 "닫힌 집합(인원수 고정)" 모드로 동작한다.
    """
    pcm16_bytes = await request.body()
    samples = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    inference = request.app.state.speaker_embedding_inference
    # 프로필 상태 없이 임베딩 추출 기능만 재사용하기 위한 임시 인스턴스
    identifier = LiveSpeakerIdentifier(inference)
    embedding = identifier.extract_embedding(samples)

    profiles = request.app.state.enrolled_profiles.setdefault(session_id, {})
    profiles[speaker_name] = embedding

    duration_sec = round(len(samples) / REALTIME_SAMPLE_RATE, 2)
    logger.info(
        f"📇 화자 사전 등록: session={session_id}, name={speaker_name}, "
        f"오디오 길이={duration_sec}s, 현재 등록 인원={len(profiles)}"
    )
    return {
        "status": "success",
        "session_id": session_id,
        "speaker_name": speaker_name,
        "registered_count": len(profiles),
        "registered_names": list(profiles.keys()),
    }


@router.get("/enroll/{session_id}")
async def get_enrolled_speakers(session_id: str, request: Request):
    """지금까지 이 session_id에 등록된 화자 목록 조회 (UI 확인용)."""
    profiles = request.app.state.enrolled_profiles.get(session_id, {})
    return {"session_id": session_id, "registered_names": list(profiles.keys())}


@router.delete("/enroll/{session_id}")
async def clear_enrolled_speakers(session_id: str, request: Request):
    """등록 초기화 (다시 등록하고 싶을 때)."""
    request.app.state.enrolled_profiles.pop(session_id, None)
    return {"status": "success", "session_id": session_id}
