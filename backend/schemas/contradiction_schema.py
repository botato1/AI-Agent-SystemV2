# backend/schemas/contradiction_schema.py

"""
모순 감지, 모순 해결 기록, 변경 반영 요약 초안과 관련된
Pydantic 스키마를 정의한다.

카테고리 범위 설계:
- contradictions에는 category_id를 별도로 저장하지 않는다.
- reference_file_id는 항상 존재하므로 workspace_files.category_id를 통해
  모순이 속한 카테고리를 확인할 수 있다.
- 카테고리별 모순 목록은 contradictions.reference_file_id와
  workspace_files.id를 조인하여 조회한다.
- 모순의 출처와 기준 파일이 동일한 workspace 및 category에
  속하는지는 서비스 계층에서 검증한다.

서비스 계층에서 다음 관계를 검증해야 한다.
- 회의 발언 출처의 meeting이 현재 workspace_id에 속하는지 확인
- 채팅 메시지 출처의 room이 현재 workspace_id에 속하는지 확인
- 출처의 category_id와 reference_file의 category_id가 일치하는지 확인
- reference_chunk_id가 reference_file_id에 속하는지 확인
- reference_code_fact_id가 reference_file_id에 속하는지 확인
- 기준 파일이 최신 버전이고 분석 완료 상태인지 확인
- 기준 파일의 contradiction_enabled가 True인지 확인

TODO:
- 모순 감지 및 해결 API의 요청·응답 스키마는
  관련 라우터 구현 시 별도로 정의
- change_summary_drafts.context_type과 meeting_summary_id, room_id의
  관계가 확정되면 Pydantic 검증과 DB CHECK 제약을 추가
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, model_validator

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
    회의 발언 또는 채팅 메시지가 문서, 코드, 설정값과
    충돌한 결과 하나를 표현한다.

    contradictions 테이블에는 created_at 컬럼이 없으므로
    detected_at과 updated_at을 직접 선언한다.
    """

    id: UUID
    workspace_id: UUID

    source_type: ContradictionSourceType
    meeting_segment_id: Optional[UUID] = None
    room_message_id: Optional[UUID] = None

    reference_type: ContradictionReferenceType
    reference_file_id: UUID
    reference_chunk_id: Optional[UUID] = None
    reference_code_fact_id: Optional[UUID] = None

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

            if self.reference_code_fact_id is not None:
                raise ValueError(
                    "reference_type이 content_chunk이면 "
                    "reference_code_fact_id는 NULL이어야 합니다."
                )

        elif self.reference_type == "code_fact":
            if self.reference_code_fact_id is None:
                raise ValueError(
                    "reference_type이 code_fact이면 "
                    "reference_code_fact_id가 필수입니다."
                )

            if self.reference_chunk_id is not None:
                raise ValueError(
                    "reference_type이 code_fact이면 "
                    "reference_chunk_id는 NULL이어야 합니다."
                )

        return self


# =============================================================================
# Re:Call: contradiction_resolutions
# =============================================================================

class ContradictionResolutionSchema(ORMBaseSchema):
    """
    모순 해결 기록 하나를 표현한다.

    contradiction_id는 contradictions.id를 참조하며,
    모순당 해결 기록 하나만 존재하도록 DB에서 UNIQUE 제약을 적용한다.

    contradiction_resolutions 테이블은 resolved_at만 가지므로
    TimestampSchema를 상속하지 않는다.
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
    사용자가 모순 해결 방식으로 '변경 인지함'을 선택한 후
    생성되는 변경 반영 요약 초안을 표현한다.

    contradiction_id와 resolution_id는 각각 UNIQUE 제약을 가지며,
    원본 문서, 코드 및 설정 파일은 직접 수정하지 않는다.

    context_type별 meeting_summary_id와 room_id의 필수 여부는
    관련 처리 흐름이 확정될 때 검증 규칙으로 추가한다.
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