# backend/schemas/file_schema.py

"""
워크스페이스 통합 파일과 관련된 Pydantic 스키마를 정의한다.

문서, 코드, 설정, 이미지, 음성 파일을
workspace_files 테이블에서 통합 관리한다.

카테고리 범위 설계:
- workspace_files.category_id는 파일이 속한 카테고리를 나타낸다.
- origin_type에 따라 category_id를 결정하는 기준이 달라진다.

    room_upload
        -> 연결된 rooms.category_id 사용

    worktree
        -> 연결된 worktrees.category_id 사용

    meeting_upload / live_recording
        -> 회의 생성 단계에서 확정된 category_id 사용
        -> meetings가 먼저 생성된 경우 meetings.category_id를 상속

    document_analysis
        -> 현재 업로드 화면의 category_id 사용
        -> 카테고리 정보가 없으면 워크스페이스의 기본 category_id 사용
        
- 확정된 category_id가 해당 workspace_id에 속하는지
  서비스 계층에서 검증한다.
- category_id 결정과 상속 처리는 서비스 계층에서 담당한다.

파일 종류별 권장 설정:
- document, code, config, image
    rag_enabled = True
    contradiction_enabled = True

- audio
    rag_enabled = False
    contradiction_enabled = False

회의 음성 파일 자체는 검색 자료로 사용하지 않는다.
STT 처리 후 생성되는 content_chunks에서 RAG 포함 여부를 별도로 관리한다.

TODO:
- 파일 업로드 및 조회 API의 요청·응답 스키마는 관련 라우터 구현 시 별도로 정의
- sha256_hash는 인덱스로 사용하되 UNIQUE 제약은 적용하지 않음
- 파일 버전 생성 시 이전 버전의 is_latest를 False로 변경
- worktree_id, category_id, origin_type 간 일관성을 서비스 계층에서 검증
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from backend.schemas.common_schema import (
    SoftDeleteSchema,
    TimestampSchema,
)
from backend.schemas.type_schema import (
    FileAnalysisStatus,
    FileKind,
    FileOriginType,
)


# =============================================================================
# Re:Call: workspace_files
# =============================================================================

class WorkspaceFileSchema(TimestampSchema, SoftDeleteSchema):
    """
    문서, 코드, 설정, 이미지, 음성 파일을 통합 관리하는 스키마.

    서비스 계층에서 파일의 origin_type에 따라
    worktree_id, category_id 및 관련 엔터티의 일관성을 검증한다.
    """

    id: UUID
    workspace_id: UUID
    category_id: UUID
    worktree_id: Optional[UUID] = None

    uploaded_by: UUID

    original_filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    relative_path: Optional[str] = None

    stored_filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    storage_path: str = Field(
        ...,
        min_length=1,
    )

    mime_type: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    extension: Optional[str] = Field(
        default=None,
        max_length=20,
    )

    file_kind: FileKind
    origin_type: FileOriginType

    file_size_bytes: int = Field(
        ...,
        ge=0,
    )
    sha256_hash: str = Field(
        ...,
        pattern=r"^[0-9a-fA-F]{64}$",
    )

    version_group_id: UUID
    version_no: int = Field(
        ...,
        ge=1,
    )
    previous_version_id: Optional[UUID] = None
    is_latest: bool

    analysis_status: FileAnalysisStatus

    rag_enabled: bool
    contradiction_enabled: bool

    retry_count: int = Field(
        ...,
        ge=0,
    )
    last_attempt_at: Optional[datetime] = None
    processing_error: Optional[str] = None