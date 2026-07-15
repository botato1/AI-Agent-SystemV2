# backend/schemas/worktree_schema.py

"""
워크트리(로컬 폴더 업로드 작업) 관련 Pydantic 스키마를 정의한다.

카테고리 범위 설계:
- worktrees.category_id는 워크트리가 속한 카테고리를 나타낸다.
- MVP에서는 워크스페이스의 기본 카테고리를 서비스 계층에서 자동 적용한다.
- 향후 카테고리를 프론트엔드에 표시하면 현재 카테고리 화면의
  category_id를 업로드 요청에 자동으로 포함한다.
- 사용자가 카테고리를 별도로 선택하는 UI는 필수 사항이 아니다.
- 워크트리에 포함된 파일은 worktrees.category_id를
  workspace_files.category_id로 상속받는다.

TODO:
- 워크트리 업로드 API의 요청·응답 스키마는 관련 라우터 구현 시 별도로 정의
- 워크트리 생성 시 category_id가 해당 workspace_id에 속하는지 서비스 계층에서 검증
- 폴더 구조 복원은 workspace_files.relative_path를 기준으로 서비스 계층에서 처리
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from backend.schemas.common_schema import TimestampSchema
from backend.schemas.type_schema import WorktreeStatus


# =============================================================================
# Re:Call: worktrees
# =============================================================================

class WorktreeSchema(TimestampSchema):
    """
    한 번의 로컬 폴더 업로드 작업과 전체 처리 상태를 표현한다.

    빈 폴더 자체는 별도로 저장하지 않는다.
    폴더 구조는 workspace_files.relative_path를 이용해 복원한다.

    서비스 계층에서 다음 관계를 검증해야 한다.

        worktrees.workspace_id == categories.workspace_id
    """

    id: UUID
    workspace_id: UUID
    category_id: UUID

    root_folder_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    uploaded_by: UUID

    total_file_count: int = Field(
        ...,
        ge=0,
    )
    completed_file_count: int = Field(
        ...,
        ge=0,
    )
    failed_file_count: int = Field(
        ...,
        ge=0,
    )
    excluded_file_count: int = Field(
        ...,
        ge=0,
    )

    status: WorktreeStatus
    completed_at: Optional[datetime] = None