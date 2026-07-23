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
