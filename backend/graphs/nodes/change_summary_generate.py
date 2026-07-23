# backend/graphs/nodes/change_summary_generate.py

# 모순을 "변경 인지함"으로 처리한 뒤 생성되는 ChangeSummaryDraft의 요약 텍스트를
# LLM으로 채우는 백그라운드 노드.
#
# contradiction_detect_node/meeting_postprocess_node와 동일한 fire-and-forget
# 패턴 — 라우터 응답과 별개로 백그라운드에서 실행되고, 프론트는
# GET .../change-summary로 폴링한다 (AI Chat 노드와 달리 동기 응답 아님).

import os
import uuid

import httpx

from backend.db.crud import contradiction_crud
from backend.db.session import SessionLocal
from backend.graphs.states.contradiction_resolution_state import ContradictionResolutionState

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

_SUMMARY_PROMPT = """당신은 팀 문서/기록의 변경사항을 정리하는 비서입니다.

[기존 내용]
{original_text}

[새로 확정된 내용]
{accepted_text}

[참고: 관련 회의 요약]
{base_summary}

위 정보를 바탕으로, 무엇이 어떻게 바뀌었는지 팀원들이 한눈에 이해할 수 있도록
간결한 한국어 문장으로 요약하세요 (2~3문장 이내). 다른 설명 없이 요약문만 답하세요."""


def build_summary_prompt(original_text: str, accepted_text: str, base_summary: str | None) -> str:
    """기존 내용 + 새로 확정된 내용 + (있으면) 관련 회의 요약을 프롬프트로 조립한다."""
    return _SUMMARY_PROMPT.format(
        original_text=original_text,
        accepted_text=accepted_text,
        base_summary=base_summary or "(추가 맥락 없음)",
    )


def _call_llm_summary(prompt: str) -> str | None:
    """Ollama에 일반 텍스트 요약 생성을 요청한다. 실패 시 None."""
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        response.raise_for_status()
        summary = response.json().get("response", "").strip()
        return summary or None
    except (httpx.HTTPError, ValueError, KeyError, AttributeError) as e:
        print(f"[change_summary_generate] LLM 호출 실패: {repr(e)}")
        return None


def change_summary_generate_node(state: ContradictionResolutionState) -> dict:
    contradiction_uuid = uuid.UUID(state["contradiction_id"])

    db = SessionLocal()
    try:
        draft = contradiction_crud.get_change_summary_draft(db, contradiction_uuid)
        if draft is None:
            return {"error": f"contradiction_id={contradiction_uuid}에 대한 변경요약 초안을 찾을 수 없습니다."}

        # 멱등성 가드 — meeting_postprocess_node의 "processing 아니면 거부"와 동일한 의도.
        # 이미 처리 중/완료/실패한 draft를 중복 실행하지 않는다.
        if draft.generation_status != "pending":
            return {
                "generated_summary": draft.generated_summary,
                "generation_status": draft.generation_status,
                "change_summary_draft_id": str(draft.id),
            }

        contradiction_crud.update_change_summary_draft(
            db, contradiction_uuid, generation_status="processing",
        )

        prompt = build_summary_prompt(
            draft.original_reference_text,
            draft.accepted_change_text,
            draft.base_summary_snapshot,
        )
        summary = _call_llm_summary(prompt)

        if summary is None:
            updated = contradiction_crud.update_change_summary_draft(
                db, contradiction_uuid,
                generation_status="failed",
                generation_error="LLM 호출 실패",
            )
            return {
                "generated_summary": None,
                "generation_status": "failed",
                "change_summary_draft_id": str(updated.id),
            }

        updated = contradiction_crud.update_change_summary_draft(
            db, contradiction_uuid,
            generated_summary=summary,
            generation_status="completed",
            model_name=OLLAMA_MODEL,
        )
        return {
            "generated_summary": summary,
            "generation_status": "completed",
            "model_name": OLLAMA_MODEL,
            "change_summary_draft_id": str(updated.id),
        }

    except Exception as e:
        # meeting_postprocess_node의 finally 패턴과 동일 — draft가 processing에
        # 영원히 멈춰있지 않도록 예상 못 한 예외도 failed로 남긴다.
        print(f"[change_summary_generate] 처리 중 예외 발생: {repr(e)}")
        try:
            contradiction_crud.update_change_summary_draft(
                db, contradiction_uuid,
                generation_status="failed",
                generation_error=repr(e),
            )
        except Exception:
            pass
        return {"error": f"변경요약 생성 중 예외 발생: {repr(e)}"}

    finally:
        db.close()
