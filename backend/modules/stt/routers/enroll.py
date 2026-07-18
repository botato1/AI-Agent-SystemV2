import asyncio
import time
from fastapi import APIRouter, Request
from typing import Optional

from ..core.config import logger
from ..services.voice_ingest import ingest_voice_sample
from ..utils.name_extractor import extract_name_from_greeting

router = APIRouter()

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
    이번 회의(session_id) 한정 화자 등록 — 전역 프로필(POST /api/profiles)을 아직 안 만든
    사람이나 일회성 참석자(게스트)용. 참석자 전원이 전역 프로필을 갖고 있다면
    이 절차 없이 WebSocket의 attendees 파라미터만으로 회의를 시작할 수 있다.

    "안녕하세요 OOO입니다" 발화를 받아 이름 자동 추출 + 목소리 지문 등록.
    이름 추출 실패 시 speaker_name 쿼리 파라미터로 직접 지정 (폴백 UI용).
    이후 같은 session_id로 WebSocket이 연결되면 이 등록 정보를 이어받아
    "닫힌 집합(인원수 고정)" 모드로 동작한다.
    """
    pcm16_bytes = await request.body()
    try:
        detected_text, embedding = await ingest_voice_sample(request.app.state, pcm16_bytes)
    except ValueError as e:
        return {"status": "error", "session_id": session_id, "message": str(e)}

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

    _prune_stale_enrollments(request.app)
    profiles = request.app.state.enrolled_profiles.setdefault(session_id, {})
    request.app.state.enrolled_at[session_id] = time.time()
    final_name = _dedupe_name(final_name, profiles)
    profiles[final_name] = embedding

    logger.info(
        f"📇 화자 사전 등록: session={session_id}, name={final_name} "
        f"(인식된 문장: \"{detected_text}\", 자동추출={'실패→수동' if name_extraction_failed else '성공'}), "
        f"현재 등록 인원={len(profiles)}"
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

    # 이미 회의가 진행 중이면 살아있는 세션(이후 자막 라벨)과 회의록(과거 세그먼트,
    # C-4용 프로필 스냅샷)에도 전파 — 안 하면 회의 시작 후 수정 시 옛 이름이 계속 남음
    active_session = request.app.state.active_sessions.get(session_id)
    if active_session is not None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, active_session.rename_speaker, old_name, new_name)

    logger.info(f"✏️ 화자 이름 수정: session={session_id}, {old_name} → {new_name}")
    return {
        "status": "success",
        "session_id": session_id,
        "speaker_name": new_name,
        "registered_names": list(profiles.keys()),
    }
