from fastapi import APIRouter, Request
from typing import Optional

from ..core.config import logger
from ..services.voice_ingest import ingest_voice_sample
from ..utils.name_extractor import extract_name_from_greeting

router = APIRouter()

# 전역 프로필 등록 시 읽는 표준 문장.
# "안녕하세요 OOO입니다"만으로는 4~5음절의 임베딩이라 발음 정보가 부족해서,
# 한국어의 다양한 모음(아/에/이/오/우/어/으)과 자음, 받침이 고르게 섞인 문장을
# 이어 읽게 해 목소리 지문의 안정성을 높인다 (약 10~12초 분량).
# 문장 첫머리의 자기소개 패턴은 이름 자동 추출(name_extractor)이 그대로 사용.
ENROLLMENT_SCRIPT = (
    "안녕하세요, OOO입니다. "
    "저는 오늘 회의에서 프로젝트 진행 상황과 다음 계획을 함께 검토하고, "
    "궁금한 점이 있으면 바로 질문하면서 적극적으로 참여하겠습니다."
)


@router.get("/profiles/script")
async def get_enrollment_script():
    """등록 시 읽을 표준 문장 — 프론트가 하드코딩하지 않고 이걸 표시하면 됨."""
    return {"script": ENROLLMENT_SCRIPT}


@router.post("/profiles")
async def register_global_profile(request: Request, speaker_name: Optional[str] = None):
    """
    전역 목소리 프로필 등록 (프로그램 최초 사용 시 1회).
    "안녕하세요 OOO입니다" 발화(PCM16LE 16kHz mono)를 바디로 받아 이름을 자동
    추출하고 목소리 지문을 영구 저장한다. 이후 회의에선 재녹음 없이
    참석자 선택만으로 이 프로필이 사용됨 (WebSocket의 attendees 파라미터).

    - 이름 자동 추출 실패 시 speaker_name 쿼리 파라미터로 직접 지정 (폴백 UI용)
    - 같은 이름으로 다시 등록하면 덮어씀 = 재등록 (감기/마이크 변경 등으로
      목소리가 달라졌을 때 갱신하는 용도라 의도된 동작)
    """
    pcm16_bytes = await request.body()
    try:
        detected_text, embedding = await ingest_voice_sample(request.app.state, pcm16_bytes)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    extracted_name = extract_name_from_greeting(detected_text)
    name_extraction_failed = extracted_name is None
    final_name = extracted_name or speaker_name

    if not final_name:
        return {
            "status": "error",
            "detected_text": detected_text,
            "name_extraction_failed": True,
            "message": "이름 자동 인식 실패. speaker_name 파라미터로 직접 지정해서 다시 요청해줘.",
        }

    try:
        final_name = request.app.state.voice_profiles.register(final_name, embedding)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    return {
        "status": "success",
        "speaker_name": final_name,
        "detected_text": detected_text,
        "name_extraction_failed": name_extraction_failed,
        "registered_names": request.app.state.voice_profiles.list_names(),
    }


@router.get("/profiles")
async def list_global_profiles(request: Request):
    """등록된 전역 프로필 이름 목록 — 회의 시작 화면의 '참석자 선택' UI가 사용."""
    return {"names": request.app.state.voice_profiles.list_names()}


@router.delete("/profiles/{name}")
async def delete_global_profile(name: str, request: Request):
    try:
        deleted = request.app.state.voice_profiles.delete(name)
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    if not deleted:
        return {"status": "error", "message": f"'{name}'은(는) 등록되어 있지 않음"}
    return {"status": "success", "registered_names": request.app.state.voice_profiles.list_names()}


@router.patch("/profiles/{name}/rename")
async def rename_global_profile(name: str, new_name: str, request: Request):
    """이름 오인식(예: 이준오→이준호) 수정용 — 목소리 지문은 그대로 두고 이름만 교체."""
    try:
        renamed = request.app.state.voice_profiles.rename(name, new_name)
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    if not renamed:
        return {"status": "error", "message": f"'{name}'은(는) 등록되어 있지 않음"}
    return {"status": "success", "registered_names": request.app.state.voice_profiles.list_names()}
