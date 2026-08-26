# backend/graphs/states/contradiction_state.py

# 회의 발화 또는 채팅 메시지 하나의 모순을 감지하는 그래프 상태.
# 사실 추출, 근거 검색, 비교, 중복 제거 및 저장 결과를 관리한다.

from typing import Any, NotRequired, Required, TypedDict

from backend.graphs.states.common_state import CommonState
from backend.schemas.type_schema import (
    ContradictionReferenceType,
    ContradictionSeverity,
    ContradictionSourceType,
)


class DetectedContradiction(TypedDict, total=False):
    reference_type: Required[ContradictionReferenceType]
    reference_file_id: Required[str]
    reference_chunk_id: NotRequired[str]
    reference_code_fact_id: NotRequired[str]

    reason: Required[str]
    confidence_score: Required[float]
    severity: Required[ContradictionSeverity]

    deduplication_key: NotRequired[str]


class ContradictionState(CommonState, total=False):
    # 감지 대상
    source_type: Required[ContradictionSourceType]
    meeting_segment_id: NotRequired[str]
    room_message_id: NotRequired[str]
    statement_text: Required[str]

    # 후보 필터 및 사실 추출
    is_candidate: NotRequired[bool]
    extracted_facts: NotRequired[list[dict[str, Any]]]

    # 근거 검색
    code_fact_candidates: NotRequired[list[dict[str, Any]]]
    content_chunk_candidates: NotRequired[list[dict[str, Any]]]

    # 규칙 및 LLM 판단
    rule_comparison_results: NotRequired[list[dict[str, Any]]]
    needs_llm_judgment: NotRequired[bool]
    llm_judgments: NotRequired[list[dict[str, Any]]]

    # 최종 모순 결과
    detected_contradictions: NotRequired[list[DetectedContradiction]]
    deduplicated_contradictions: NotRequired[list[DetectedContradiction]]

    # 저장 및 알림 결과
    saved_contradiction_ids: NotRequired[list[str]]
    notification_ids: NotRequired[list[str]]