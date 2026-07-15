# backend/schemas/action_item_schema.py

"""
할 일(action_items) 관련 Pydantic 스키마를 정의한다.

카테고리 범위 설계:
- action_items.category_id는 할 일이 속한 카테고리를 나타낸다.
- 회의에서 추출한 할 일은 meetings.category_id를 복사하여 저장한다.
- 사용자가 직접 생성한 할 일은 MVP에서 워크스페이스의 기본
  category_id를 서비스 계층에서 자동 적용한다.
- 향후 여러 카테고리를 지원할 때는 현재 화면의 카테고리를 적용하거나
  사용자가 선택한 category_id를 사용한다.
- meeting_id가 없는 직접 생성 할 일은 다른 테이블을 통해 category_id를
  유도할 수 없으므로 action_items에 category_id를 직접 저장한다.

서비스 계층에서 다음 관계를 검증해야 한다.
- action_items.category_id가 action_items.workspace_id에 속하는지 확인
- meeting_id가 있으면 action_items.workspace_id와
  meetings.workspace_id가 일치하는지 확인
- meeting_id가 있으면 action_items.category_id와
  meetings.category_id가 일치하는지 확인
- source_segment_id가 있으면 해당 세그먼트가 meeting_id의 회의에
  속하는지 확인

TODO:
- 할 일 생성, 수정, 조회 API의 요청·응답 스키마는
  관련 라우터 구현 시 별도로 정의
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, model_validator, BaseModel

from backend.schemas.common_schema import (
    ORMBaseSchema,
    SoftDeleteSchema,
    TimestampSchema,
)
from backend.schemas.type_schema import (
    ActionItemPriority,
    ActionItemStatus,
)


# =============================================================================
# Re:Call: action_items
# =============================================================================

class ActionItemSchema(TimestampSchema, SoftDeleteSchema):
    """
    회의에서 추출되었거나 사용자가 직접 생성한 할 일 하나를 표현한다.

    meeting_id가 NULL이면 사용자가 직접 만든 할 일이다.
    source_segment_id는 회의 발언에서 추출된 할 일에만 사용한다.
    """

    id: UUID
    workspace_id: UUID
    category_id: UUID

    meeting_id: Optional[UUID] = None
    source_segment_id: Optional[UUID] = None

    assignee_id: Optional[UUID] = None
    assignee_label: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )
    description: Optional[str] = None

    priority: Optional[ActionItemPriority] = None
    status: ActionItemStatus

    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    created_by: Optional[UUID] = None

    @model_validator(mode="after")
    def _validate_source_consistency(self) -> "ActionItemSchema":
        if self.source_segment_id is not None and self.meeting_id is None:
            raise ValueError(
                "source_segment_id가 있으면 meeting_id도 필수입니다."
            )

        return self

# =============================================================================
# Re:Call: action_items API 요청/응답
# =============================================================================

class ActionItemCreateRequest(BaseModel):
    """사용자가 직접 생성하는 할 일 요청. meeting_id/category_id는 서비스 계층에서 채운다."""

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    assignee_id: Optional[UUID] = None
    assignee_label: Optional[str] = Field(default=None, max_length=100)
    priority: Optional[ActionItemPriority] = None
    due_at: Optional[datetime] = None


class ActionItemStatusUpdateRequest(BaseModel):
    status: ActionItemStatus


class ActionItemPriorityUpdateRequest(BaseModel):
    priority: ActionItemPriority


class ActionItemResponse(ORMBaseSchema):
    id: UUID
    workspace_id: UUID
    meeting_id: Optional[UUID] = None

    title: str
    description: Optional[str] = None

    assignee_id: Optional[UUID] = None
    assignee_label: Optional[str] = None

    priority: Optional[ActionItemPriority] = None
    status: ActionItemStatus

    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class ActionItemListResponse(BaseModel):
    action_items: list[ActionItemResponse] = Field(default_factory=list)