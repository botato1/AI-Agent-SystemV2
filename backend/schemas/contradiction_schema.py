# backend/schemas/contradiction_schema.py

"""
모순 감지, 해결 기록, 변경 반영 요약 초안 스키마를 정의한다.
모순은 workspace_id와 category_id를 기준으로 조회하고 격리한다.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.schemas.common_schema import (
    ORMBaseSchema,
    TimestampSchema,
)
from backend.schemas.type_schema import (
    ChangeSummaryContextType,
    ContradictionReferenceType,
    ContradictionResolutionType,
    ContradictionSeverity,
    ContradictionSourceType,
    ContradictionStatus,
    GenerationStatus,
)


# =============================================================================
# Re:Call: contradictions
# =============================================================================

class ContradictionSchema(ORMBaseSchema):
    """
    회의 발언 또는 채팅 메시지와 기준 자료의 모순 결과를 표현한다.
    출처와 기준 자료는 동일한 workspace 및 category에 속해야 한다.
    """

    id: UUID
    workspace_id: UUID
    category_id: UUID

    source_type: ContradictionSourceType
    meeting_segment_id: Optional[UUID] = None
    room_message_id: Optional[UUID] = None
    session_meeting_id: Optional[UUID] = None
    session_room_id: Optional[UUID] = None

    reference_type: ContradictionReferenceType
    reference_file_id: Optional[UUID] = None
    reference_chunk_id: Optional[UUID] = None
    reference_code_fact_id: Optional[UUID] = None
    reference_decision_id: Optional[UUID] = None

    statement_text_snapshot: str = Field(
        ...,
        min_length=1,
    )
    reference_text_snapshot: str = Field(
        ...,
        min_length=1,
    )
    reference_location: Optional[dict[str, Any]] = None
    reason: Optional[str] = None

    confidence_score: Decimal = Field(
        ...,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )
    severity: ContradictionSeverity

    deduplication_key: str = Field(
        ...,
        min_length=1,
        max_length=64,
    )
    cooldown_until: Optional[datetime] = None
    status: ContradictionStatus

    detected_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _validate_source_type(self) -> "ContradictionSchema":
        if self.source_type == "meeting_segment":
            if self.meeting_segment_id is None:
                raise ValueError(
                    "source_type이 meeting_segment이면 "
                    "meeting_segment_id가 필수입니다."
                )

            if self.room_message_id is not None:
                raise ValueError(
                    "source_type이 meeting_segment이면 "
                    "room_message_id는 NULL이어야 합니다."
                )

        elif self.source_type == "room_message":
            if self.room_message_id is None:
                raise ValueError(
                    "source_type이 room_message이면 "
                    "room_message_id가 필수입니다."
                )

            if self.meeting_segment_id is not None:
                raise ValueError(
                    "source_type이 room_message이면 "
                    "meeting_segment_id는 NULL이어야 합니다."
                )

        return self

    @model_validator(mode="after")
    def _validate_reference_type(self) -> "ContradictionSchema":
        if self.reference_type == "content_chunk":
            if self.reference_chunk_id is None:
                raise ValueError(
                    "reference_type이 content_chunk이면 "
                    "reference_chunk_id가 필수입니다."
                )

            if self.reference_code_fact_id is not None or self.reference_decision_id is not None:
                raise ValueError(
                    "reference_type이 content_chunk이면 "
                    "reference_code_fact_id/reference_decision_id는 NULL이어야 합니다."
                )

        elif self.reference_type == "code_fact":
            if self.reference_code_fact_id is None:
                raise ValueError(
                    "reference_type이 code_fact이면 "
                    "reference_code_fact_id가 필수입니다."
                )

            if self.reference_chunk_id is not None or self.reference_decision_id is not None:
                raise ValueError(
                    "reference_type이 code_fact이면 "
                    "reference_chunk_id/reference_decision_id는 NULL이어야 합니다."
                )

        elif self.reference_type == "decision":
            if self.reference_decision_id is None:
                raise ValueError(
                    "reference_type이 decision이면 "
                    "reference_decision_id가 필수입니다."
                )

            if self.reference_chunk_id is not None or self.reference_code_fact_id is not None:
                raise ValueError(
                    "reference_type이 decision이면 "
                    "reference_chunk_id/reference_code_fact_id는 NULL이어야 합니다."
                )

        return self


# =============================================================================
# Re:Call: contradiction_resolutions
# =============================================================================

class ContradictionResolutionSchema(ORMBaseSchema):
    """
    모순 해결 기록 하나를 표현한다.
    모순당 해결 기록 하나만 저장한다.
    """

    id: UUID
    contradiction_id: UUID
    resolved_by: UUID

    resolution_type: ContradictionResolutionType
    note: Optional[str] = None

    resolved_at: datetime


# =============================================================================
# Re:Call: change_summary_drafts
# =============================================================================

class ChangeSummaryDraftSchema(TimestampSchema):
    """
    변경 인지 처리 후 생성되는 변경 반영 요약 초안을 표현한다.
    원본 문서, 코드 및 설정 파일은 직접 수정하지 않는다.
    """

    id: UUID
    workspace_id: UUID

    contradiction_id: UUID
    resolution_id: UUID

    context_type: ChangeSummaryContextType
    meeting_summary_id: Optional[UUID] = None
    room_id: Optional[UUID] = None

    original_reference_text: str = Field(
        ...,
        min_length=1,
    )
    accepted_change_text: str = Field(
        ...,
        min_length=1,
    )

    base_summary_snapshot: Optional[str] = None
    generated_summary: Optional[str] = None

    generation_status: GenerationStatus
    generation_error: Optional[str] = None

    model_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    
# =============================================================================
# Re:Call: contradictions API 요청/응답
# =============================================================================

class ContradictionListResponse(BaseModel):
    contradictions: list[ContradictionSchema] = Field(default_factory=list)


class ContradictionResolveRequest(BaseModel):
    resolution_type: ContradictionResolutionType
    note: Optional[str] = None