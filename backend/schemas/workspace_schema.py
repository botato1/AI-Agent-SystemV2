# backend/schemas/workspace_schema.py

"""
워크스페이스, 워크스페이스 멤버, 카테고리, 채팅방과 관련된
Pydantic 스키마를 정의한다.

MVP 기준:
- 워크스페이스 생성 시 기본 카테고리 1개를 자동 생성한다.
- 기본 카테고리는 is_default=True, display_order=0으로 생성한다.
- 카테고리는 백엔드 데이터 구조에 유지하되 프론트엔드에는 표시하지 않는다.
- rooms.rag_enabled는 사용하지 않는다.
- 채팅 메시지는 RAG 검색 자료로 사용하지 않는다.

TODO:
- 워크스페이스, 멤버, 카테고리, 채팅방 API의 생성·수정·응답
  스키마는 관련 라우터와 서비스 구현 시 별도로 정의한다.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, BaseModel

from backend.schemas.common_schema import (
    ORMBaseSchema,
    SoftDeleteSchema,
    TimestampSchema,
)
from backend.schemas.type_schema import WorkspaceRole


# =============================================================================
# Re:Call: workspaces
# =============================================================================

class WorkspaceSchema(TimestampSchema, SoftDeleteSchema):
    """워크스페이스의 전체 저장 정보를 표현한다."""

    id: UUID
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )
    description: Optional[str] = None
    owner_id: UUID


# =============================================================================
# Re:Call: workspace_members
# =============================================================================

class WorkspaceMemberSchema(ORMBaseSchema):
    """
    워크스페이스 멤버 정보를 표현한다.

    한 사용자는 동일한 워크스페이스에 한 번만 소속될 수 있다.

    DB 제약조건:
        UNIQUE(workspace_id, user_id)

    해당 테이블은 created_at과 updated_at 대신
    joined_at과 removed_at을 사용한다.
    """

    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    added_by: UUID
    joined_at: datetime
    removed_at: Optional[datetime] = None


# =============================================================================
# Re:Call: categories
# =============================================================================

class CategorySchema(TimestampSchema, SoftDeleteSchema):
    """
    워크스페이스 카테고리 정보를 표현한다.

    워크스페이스 생성 시 다음 값을 가진 기본 카테고리 하나를
    서비스 계층에서 자동 생성한다.

        name = "default"
        is_default = True
        display_order = 0

    활성 상태인 기본 카테고리는 워크스페이스당 하나만 존재해야 한다.
    """

    id: UUID
    workspace_id: UUID
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )
    is_default: bool
    display_order: int = Field(
        ...,
        ge=0,
    )
    created_by: UUID


# =============================================================================
# Re:Call: rooms
# =============================================================================

class RoomSchema(TimestampSchema, SoftDeleteSchema):
    """
    채팅방 정보를 표현한다.

    서비스 계층에서 다음 관계를 검증해야 한다.

        rooms.workspace_id == categories.workspace_id

    rag_enabled 필드는 사용하지 않는다.
    채팅 메시지는 모순 감지 대상이지만 RAG 검색 자료는 아니다.
    """

    id: UUID
    workspace_id: UUID
    category_id: UUID
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )
    created_by: UUID

class RoomResponse(ORMBaseSchema):
    id: UUID
    workspace_id: UUID
    name: str
    created_by: UUID
    created_at: datetime


class RoomListResponse(BaseModel):
    rooms: list[RoomResponse] = Field(default_factory=list)