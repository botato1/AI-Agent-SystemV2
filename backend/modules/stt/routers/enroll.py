import numpy as np
from fastapi import APIRouter, Request
from typing import Optional

from ..core.config import logger, REALTIME_SAMPLE_RATE, WHISPER_LANGUAGE, FAST_BEAM_SIZE
from ..services.speaker_id_service import LiveSpeakerIdentifier
from ..utils.name_extractor import extract_name_from_greeting

router = APIRouter()


@router.post("/enroll/{session_id}")
async def enroll_speaker(session_id: str, request: Request, speaker_name: Optional[str] = None):
    """
    회의 시작 전, 참석자가 "안녕하세요 OOO입니다"라고 말한 PCM16LE(16kHz, mono)
    오디오를 요청 바디로 받아:
      1. STT로 텍스트를 뽑고, 그 안에서 이름을 자동 추출
      2. 같은 오디오에서 화자 임베딩("목소리 지문")도 함께 추출
      3. 추출된 이름으로 화자 프로필을 등록
    이름 자동 추출이 실패하면(발음이 뭉개지는 등) speaker_name 쿼리 파라미터로
    수동 지정한 값을 대신 쓴다 (프론트의 "직접 입력" 폴백 UI용).

    같은 session_id로 여러 명을 순서대로 등록할 수 있고, 이후 실시간
    WebSocket(/api/ws/stt/{session_id})이 같은 session_id로 연결되면
    이 등록 정보를 그대로 이어받아 "닫힌 집합(인원수 고정)" 모드로 동작한다.
    """
    pcm16_bytes = await request.body()
    samples = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    duration_sec = round(len(samples) / REALTIME_SAMPLE_RATE, 2)

    # 1. STT로 자기소개 문장 인식 (Fast 모델로 충분 - 짧은 문장 하나뿐)
    fast_model = request.app.state.stt_model_fast
    segments, _info = fast_model.transcribe(
        samples,
        language=WHISPER_LANGUAGE,
        beam_size=FAST_BEAM_SIZE,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    detected_text = " ".join(seg.text.strip() for seg in segments).strip()

    # 2. 텍스트에서 이름 자동 추출, 실패하면 수동 입력값으로 폴백
    extracted_name = extract_name_from_greeting(detected_text)
    name_extraction_failed = extracted_name is None
    final_name = extracted_name or speaker_name

    if not final_name:
        return {
            "status": "error",
            "session_id": session_id,
            "detected_text": detected_text,
            "name_extraction_failed": True,
            "message": "이름 자동 인식 실패. speaker_name 파라미터로 직접 지정해서 다시 요청해줘.",
        }

    # 3. 화자 임베딩 추출 및 등록
    inference = request.app.state.speaker_embedding_inference
    identifier = LiveSpeakerIdentifier(inference)  # 프로필 상태 없이 임베딩 추출 기능만 재사용
    embedding = identifier.extract_embedding(samples)

    profiles = request.app.state.enrolled_profiles.setdefault(session_id, {})
    profiles[final_name] = embedding

    logger.info(
        f"📇 화자 사전 등록: session={session_id}, name={final_name} "
        f"(인식된 문장: \"{detected_text}\", 자동추출={'실패→수동' if name_extraction_failed else '성공'}), "
        f"오디오 길이={duration_sec}s, 현재 등록 인원={len(profiles)}"
    )
    return {
        "status": "success",
        "session_id": session_id,
        "speaker_name": final_name,
        "detected_text": detected_text,
        "name_extraction_failed": name_extraction_failed,
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
