"""모순 감지 — 내 파트

Contradiction:            발언/메시지 vs 문서/코드/설정값 충돌
ContradictionResolution:  처리 결과 (변경 인지함 / 기준 유지)
ChangeSummaryDraft:       변경 인지함 처리 후 생성되는 요약 초안
"""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class Contradiction(Base):
    __tablename__ = "contradictions"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    source_type = Column(String(30), nullable=False)
    meeting_segment_id = Column(UUID(as_uuid=True), ForeignKey("meeting_segments.id"), nullable=True)
    room_message_id = Column(UUID(as_uuid=True), ForeignKey("room_messages.id"), nullable=True)
    reference_type = Column(String(30), nullable=False)
    reference_file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    reference_chunk_id = Column(UUID(as_uuid=True), ForeignKey("content_chunks.id"), nullable=True)
    reference_code_fact_id = Column(UUID(as_uuid=True), ForeignKey("code_facts.id"), nullable=True)
    statement_text_snapshot = Column(Text, nullable=False)
    reference_text_snapshot = Column(Text, nullable=False)
    reference_location = Column(JSONB, nullable=True)
    reason = Column(Text, nullable=True)
    confidence_score = Column(Numeric(5, 4), nullable=False)
    severity = Column(String(20), nullable=False, server_default="medium")
    deduplication_key = Column(String(64), nullable=False)
    cooldown_until = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="unresolved")
    detected_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('meeting_segment','room_message')",
            name="chk_contradictions_source_type",
        ),
        CheckConstraint(
            "reference_type IN ('content_chunk','code_fact')",
            name="chk_contradictions_reference_type",
        ),
        CheckConstraint("severity IN ('low','medium','high')", name="chk_contradictions_severity"),
        CheckConstraint(
            "status IN ('unresolved','resolved','dismissed')", name="chk_contradictions_status"
        ),
        CheckConstraint(
            "(source_type = 'meeting_segment' AND meeting_segment_id IS NOT NULL "
            "AND room_message_id IS NULL) OR "
            "(source_type = 'room_message' AND room_message_id IS NOT NULL "
            "AND meeting_segment_id IS NULL)",
            name="chk_contradictions_source_exclusive",
        ),
        CheckConstraint(
            "(reference_type = 'content_chunk' AND reference_chunk_id IS NOT NULL "
            "AND reference_code_fact_id IS NULL) OR "
            "(reference_type = 'code_fact' AND reference_code_fact_id IS NOT NULL "
            "AND reference_chunk_id IS NULL)",
            name="chk_contradictions_reference_exclusive",
        ),
        Index("idx_contradictions_workspace", "workspace_id", "status", "detected_at"),
        Index("idx_contradictions_reference_file", "reference_file_id", "detected_at"),
    )


class ContradictionResolution(Base):
    __tablename__ = "contradiction_resolutions"

    id = uuid_pk()
    contradiction_id = Column(
        UUID(as_uuid=True), ForeignKey("contradictions.id"), nullable=False, unique=True
    )
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    resolution_type = Column(String(30), nullable=False)
    note = Column(Text, nullable=True)
    resolved_at = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "resolution_type IN ('change_acknowledged','keep_reference')",
            name="chk_contradiction_resolutions_type",
        ),
    )


class ChangeSummaryDraft(Base):
    """change_acknowledged 선택 시에만 생성. 원본 문서/코드는 수정하지 않는다."""

    __tablename__ = "change_summary_drafts"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    contradiction_id = Column(
        UUID(as_uuid=True), ForeignKey("contradictions.id"), nullable=False, unique=True
    )
    resolution_id = Column(
        UUID(as_uuid=True), ForeignKey("contradiction_resolutions.id"), nullable=False, unique=True
    )
    context_type = Column(String(20), nullable=False)
    meeting_summary_id = Column(UUID(as_uuid=True), ForeignKey("meeting_summaries.id"), nullable=True)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=True)
    original_reference_text = Column(Text, nullable=False)
    accepted_change_text = Column(Text, nullable=False)
    base_summary_snapshot = Column(Text, nullable=True)
    generated_summary = Column(Text, nullable=True)
    generation_status = Column(String(20), nullable=False, server_default="pending")
    generation_error = Column(Text, nullable=True)
    model_name = Column(String(100), nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        CheckConstraint("context_type IN ('meeting','chat')", name="chk_change_summary_drafts_context"),
        CheckConstraint(
            "generation_status IN ('pending','processing','completed','failed')",
            name="chk_change_summary_drafts_status",
        ),
    )
