"""음성 회의 / 결정사항 / 할 일"""

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class Meeting(Base):
    __tablename__ = "meetings"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    related_room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=True)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=True)
    title = Column(String(200), nullable=False)
    input_type = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, server_default="created")
    started_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(BigInteger, nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "input_type IN ('live_recording','audio_upload','document_upload')",
            name="chk_meetings_input_type",
        ),
        CheckConstraint(
            "status IN ('created','recording','processing','completed','failed','cancelled')",
            name="chk_meetings_status",
        ),
        Index(
            "idx_meetings_workspace", "workspace_id", "started_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_meetings_category", "category_id", "started_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class MeetingSegment(Base):
    __tablename__ = "meeting_segments"

    id = uuid_pk()
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id"), nullable=False)
    speaker_label = Column(String(50), nullable=True)
    speaker_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    start_ms = Column(BigInteger, nullable=False)
    end_ms = Column(BigInteger, nullable=False)
    segment_index = Column(Integer, nullable=False)
    stt_confidence = Column(Numeric(5, 4), nullable=True)
    language_code = Column(String(20), nullable=True)
    is_edited = Column(Boolean, nullable=False, server_default="false")
    created_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        UniqueConstraint("meeting_id", "segment_index", name="uq_meeting_segments_index"),
        CheckConstraint("end_ms > start_ms", name="chk_meeting_segments_time_order"),
        Index("idx_meeting_segments_meeting", "meeting_id", "segment_index"),
    )


class MeetingSummary(Base):
    __tablename__ = "meeting_summaries"

    id = uuid_pk()
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id"), nullable=False, unique=True)
    full_summary = Column(Text, nullable=True)
    short_summary = Column(Text, nullable=True)
    discussion_points = Column(JSONB, nullable=True)
    full_transcript = Column(Text, nullable=True)
    generation_status = Column(String(20), nullable=False, server_default="pending")
    generation_error = Column(Text, nullable=True)
    model_name = Column(String(100), nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        CheckConstraint(
            "generation_status IN ('pending','processing','completed','failed')",
            name="chk_meeting_summaries_status",
        ),
    )


class Decision(Base):
    """MVP: post-meeting 추출된 결정사항만 저장. 채팅에서는 결정 추출 안 함."""

    __tablename__ = "decisions"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id"), nullable=False)
    source_segment_id = Column(UUID(as_uuid=True), ForeignKey("meeting_segments.id"), nullable=True)
    title = Column(String(200), nullable=False)
    decision_text = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, server_default="active")
    supersedes_decision_id = Column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=True)
    confidence_score = Column(Numeric(5, 4), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False)
    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('active','superseded','cancelled')", name="chk_decisions_status"),
        Index(
            "idx_decisions_meeting", "meeting_id", "decided_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Task(Base):
    """meeting_id = NULL이면 사용자가 직접 만든 항목."""

    __tablename__ = "tasks"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id"), nullable=True)
    source_segment_id = Column(UUID(as_uuid=True), ForeignKey("meeting_segments.id"), nullable=True)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assignee_label = Column(String(100), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, server_default="open")
    due_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','in_progress','done','cancelled')", name="chk_tasks_status"
        ),
        CheckConstraint(
            "priority IS NULL OR priority IN ('low','medium','high')",
            name="chk_tasks_priority",
        ),
        Index(
            "idx_tasks_workspace", "workspace_id", "status", "due_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "idx_tasks_category", "category_id", "status", "due_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )