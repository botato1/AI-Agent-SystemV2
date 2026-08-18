# backend/graphs/states/meeting_postprocess_state.py

# 회의 종료 또는 음성 업로드 후 STT, 요약, 벡터화를 처리하는 상태.
# 결정사항과 할 일 추출 결과도 함께 관리한다.

from typing import Any, NotRequired, Required

from backend.graphs.states.common_state import CommonState
from backend.schemas.type_schema import GenerationStatus


class MeetingPostprocessState(CommonState, total=False):
    # 대상 회의
    meeting_id: Required[str]
    source_file_id: Required[str]

    # STT 처리 결과
    transcription_segments: NotRequired[list[dict[str, Any]]]
    full_transcript: NotRequired[str]
    meeting_segment_ids: NotRequired[list[str]]

    # 발화 세그먼트 청크 및 임베딩
    segment_chunk_ids: NotRequired[list[str]]
    segment_chroma_ids: NotRequired[list[str]]

    # 회의 요약 생성
    meeting_purpose: NotRequired[str]
    full_summary: NotRequired[str]
    short_summary: NotRequired[str]
    discussion_points: NotRequired[Any]
    next_steps: NotRequired[str]
    summary_model_name: NotRequired[str]
    summary_generation_status: NotRequired[GenerationStatus]
    summary_generation_error: NotRequired[str]
    meeting_summary_id: NotRequired[str]

    # 회의 요약 청크 및 임베딩
    summary_chunk_ids: NotRequired[list[str]]
    summary_chroma_ids: NotRequired[list[str]]
    embedding_model_name: NotRequired[str]

    # 결정사항 및 할 일 추출
    extracted_decisions: NotRequired[list[dict[str, Any]]]
    decision_ids: NotRequired[list[str]]
    extracted_tasks: NotRequired[list[dict[str, Any]]]
    task_ids: NotRequired[list[str]]