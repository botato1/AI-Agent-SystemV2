"""워크트리(폴더 업로드) / 통합 파일 관리 / 파일-채팅방 연결"""

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class Worktree(Base):
    """한 번의 로컬 폴더 업로드 작업과 전체 처리 상태."""

    __tablename__ = "worktrees"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    root_folder_name = Column(String(255), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    total_file_count = Column(Integer, nullable=False, server_default="0")
    completed_file_count = Column(Integer, nullable=False, server_default="0")
    failed_file_count = Column(Integer, nullable=False, server_default="0")
    excluded_file_count = Column(Integer, nullable=False, server_default="0")
    status = Column(String(30), nullable=False, server_default="pending")
    created_at = created_at_col()
    updated_at = updated_at_col()
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','completed','partially_completed','failed')",
            name="chk_worktrees_status",
        ),
        Index("idx_worktrees_workspace", "workspace_id", "created_at"),
    )


class WorkspaceFile(Base):
    """문서/코드/설정/이미지/음성 파일 통합 관리 핵심 테이블."""

    __tablename__ = "workspace_files"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    worktree_id = Column(UUID(as_uuid=True), ForeignKey("worktrees.id"), nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    original_filename = Column(String(255), nullable=False)
    relative_path = Column(Text, nullable=True)
    stored_filename = Column(String(255), nullable=False)
    storage_path = Column(Text, nullable=False)
    mime_type = Column(String(100), nullable=True)
    extension = Column(String(20), nullable=True)

    file_kind = Column(String(20), nullable=False)
    origin_type = Column(String(30), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    sha256_hash = Column(String(64), nullable=False)
    external_ref = Column(String(255), nullable=True)
    related_meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id"), nullable=True)

    version_group_id = Column(UUID(as_uuid=True), nullable=False)
    version_no = Column(Integer, nullable=False, server_default="1")
    previous_version_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=True)
    is_latest = Column(Boolean, nullable=False, server_default="true")

    analysis_status = Column(String(20), nullable=False, server_default="pending")
    rag_enabled = Column(Boolean, nullable=False, server_default="true")
    contradiction_enabled = Column(Boolean, nullable=False, server_default="true")

    retry_count = Column(Integer, nullable=False, server_default="0")
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    processing_error = Column(Text, nullable=True)

    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "file_kind IN ('document','code','config','image','audio')",
            name="chk_workspace_files_kind",
        ),
        CheckConstraint(
            "origin_type IN ('worktree','document_analysis','room_upload',"
            "'meeting_upload','live_recording','meeting_summary','meeting_export')",
            name="chk_workspace_files_origin",
        ),
        CheckConstraint(
            "analysis_status IN ('pending','processing','completed','failed','excluded')",
            name="chk_workspace_files_analysis_status",
        ),
        Index(
            "idx_workspace_files_workspace_kind", "workspace_id", "file_kind", "analysis_status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_workspace_files_category", "category_id", "analysis_status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_workspace_files_worktree_path", "worktree_id", "relative_path",
            postgresql_where=text("worktree_id IS NOT NULL"),
        ),
        Index("idx_workspace_files_hash", "workspace_id", "sha256_hash"),
        Index(
            "idx_workspace_files_reference", "workspace_id", "contradiction_enabled",
            "is_latest", "analysis_status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_workspace_files_rag", "workspace_id", "rag_enabled", "is_latest", "analysis_status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class RoomFileLink(Base):
    """파일-채팅방 연결. 파일 원본은 한 번만 저장."""

    __tablename__ = "room_file_links"

    id = uuid_pk()
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    upload_message_id = Column(UUID(as_uuid=True), ForeignKey("room_messages.id"), nullable=True)
    analysis_message_id = Column(UUID(as_uuid=True), ForeignKey("room_messages.id"), nullable=True)
    linked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = created_at_col()

    __table_args__ = (
        UniqueConstraint("room_id", "file_id", name="uq_room_file_links"),
        Index("idx_room_file_links_room", "room_id", "created_at"),
    )