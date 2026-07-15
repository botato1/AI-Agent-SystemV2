# backend/graphs/states/contradiction_resolution_state.py

# 모순 하나의 해결 기록과 변경 요약 초안 생성 상태.
# 변경 인지 처리일 때만 변경 요약 초안을 생성한다.

from typing import NotRequired, Required

from backend.graphs.states.common_state import CommonState
from backend.schemas.type_schema import (
    ChangeSummaryContextType,
    ContradictionResolutionType,
    ContradictionStatus,
    GenerationStatus,
)


class ContradictionResolutionState(CommonState, total=False):
    # 해결 대상
    contradiction_id: Required[str]
    resolution_type: Required[ContradictionResolutionType]
    resolved_by: Required[str]
    note: NotRequired[str]

    # 해결 기록 저장 결과
    resolution_id: NotRequired[str]
    contradiction_status: NotRequired[ContradictionStatus]

    # 변경 요약 초안
    context_type: NotRequired[ChangeSummaryContextType]
    meeting_summary_id: NotRequired[str]
    room_id: NotRequired[str]
    original_reference_text: NotRequired[str]
    accepted_change_text: NotRequired[str]
    base_summary_snapshot: NotRequired[str]
    generated_summary: NotRequired[str]
    generation_status: NotRequired[GenerationStatus]
    generation_error: NotRequired[str]
    model_name: NotRequired[str]
    change_summary_draft_id: NotRequired[str]