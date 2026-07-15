import asyncio
import time
import numpy as np
from fastapi import APIRouter, Request
from typing import Optional

from ..core.config import logger, REALTIME_SAMPLE_RATE, WHISPER_LANGUAGE, FAST_BEAM_SIZE
from ..services.speaker_id_service import LiveSpeakerIdentifier
from ..utils.name_extractor import extract_name_from_greeting

router = APIRouter()

MIN_ENROLL_SEC = 0.5      # 이보다 짧은 오디오는 목소리 지문을 뽑기엔 정보가 부족함
ENROLL_TTL_SEC = 2 * 3600  # 등록만 하고 회의를 시작 안 한 세션은 이 시간 뒤 자동 정리


def _prune_stale_enrollments(app) -> None:
    """등록 후 회의를 시작하지 않고 방치된 세션이 메모리에 영구히 쌓이는 걸 방지."""
    now = time.time()
    stale = [sid for sid, ts in app.state.enrolled_at.items() if now - ts > ENROLL_TTL_SEC]
    for sid in stale:
        app.state.enrolled_profiles.pop(sid, None)
        app.state.enrolled_at.pop(sid, None)
        logger.info(f"🧹 방치된 화자 등록 세션 정리: {sid}")


def _dedupe_name(name: str, existing: dict) -> str:
    """동명이인 등록 시 이전 사람 프로필을 조용히 덮어쓰지 않도록 이름 뒤에 번호를 붙임."""
    if name not in existing:
        return name
    n = 2
    while f"{name}{n}" in existing:
        n += 1
    return f"{name}{n}"


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

    # 입력 검증: PCM16은 샘플당 2바이트라 홀수 길이는 깨진 데이터,
    # 너무 짧은 오디오는 임베딩 품질이 나빠 등록 의미가 없음
    if len(pcm16_bytes) % 2 != 0:
        return {"status": "error", "session_id": session_id,
                "message": "오디오 데이터가 손상됨 (PCM16은 짝수 바이트여야 함)"}
    samples = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    duration_sec = round(len(samples) / REALTIME_SAMPLE_RATE, 2)
    if duration_sec < MIN_ENROLL_SEC:
        return {"status": "error", "session_id": session_id,
                "message": f"오디오가 너무 짧음 ({duration_sec}s < {MIN_ENROLL_SEC}s). 다시 녹음해줘."}

    loop = asyncio.get_event_loop()

    # GPU 작업(STT, 임베딩)을 executor로 — async 핸들러에서 직접 호출하면
    # 몇 초간 이벤트 루프 전체가 멈춰서 진행 중인 다른 회의의 실시간 스트리밍까지 얼어붙음
    fast_model = request.app.state.stt_model_fast

    def _run_stt() -> str:
        segments, _info = fast_model.transcribe(
            samples,
            language=WHISPER_LANGUAGE,
            beam_size=FAST_BEAM_SIZE,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    detected_text = await loop.run_in_executor(None, _run_stt)

    # 텍스트에서 이름 자동 추출, 실패하면 수동 입력값으로 폴백
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

    inference = request.app.state.speaker_embedding_inference
    identifier = LiveSpeakerIdentifier(inference)  # 프로필 상태 없이 임베딩 추출 기능만 재사용
    embedding = await loop.run_in_executor(None, identifier.extract_embedding, samples)

    _prune_stale_enrollments(request.app)
    profiles = request.app.state.enrolled_profiles.setdefault(session_id, {})
    request.app.state.enrolled_at[session_id] = time.time()
    final_name = _dedupe_name(final_name, profiles)
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


@router.patch("/enroll/{session_id}/rename")
async def rename_enrolled_speaker(session_id: str, request: Request, old_name: str, new_name: str):
    """
    이름은 인식됐지만 틀리게 인식된 경우(예: "이준오"→"이준호")를 위한 수정 엔드포인트.
    발음이 비슷한 이름은 STT가 원천적으로 헷갈릴 수 있어서, 등록 성공 여부와
    무관하게 언제든 이름만 바꿀 수 있게 함 — 재녹음 없이 이미 추출된 목소리
    지문(임베딩)은 그대로 두고 키(이름)만 교체.
    """
    profiles = request.app.state.enrolled_profiles.get(session_id, {})
    if old_name not in profiles:
        return {"status": "error", "session_id": session_id,
                "message": f"'{old_name}'은(는) 등록되어 있지 않음"}

    embedding = profiles.pop(old_name)
    new_name = _dedupe_name(new_name, profiles)
    profiles[new_name] = embedding

    logger.info(f"✏️ 화자 이름 수정: session={session_id}, {old_name} → {new_name}")
    return {
        "status": "success",
        "session_id": session_id,
        "speaker_name": new_name,
        "registered_names": list(profiles.keys()),
    }
