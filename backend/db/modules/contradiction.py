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
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    source_type = Column(String(30), nullable=False)
    meeting_segment_id = Column(UUID(as_uuid=True), ForeignKey("meeting_segments.id"), nullable=True)
    room_message_id = Column(UUID(as_uuid=True), ForeignKey("room_messages.id"), nullable=True)
    # [추가 - 2026.07.16] 세션 스코프 반정규화 (related_history_matches와 동일 패턴).
    # "세션 내 같은 decision에 대해 모순 팝업은 1회만" 규칙을 매번 join 없이 빠르게
    # 체크하기 위함 (source_type에 따라 둘 중 하나만 채워짐).
    session_meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id"), nullable=True)
    session_room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=True)
    reference_type = Column(String(30), nullable=False)
    # [수정 - 2026.07.16] decision 대비 모순은 workspace_file이 없으므로 nullable로 변경
    reference_file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=True)
    reference_chunk_id = Column(UUID(as_uuid=True), ForeignKey("content_chunks.id"), nullable=True)
    reference_code_fact_id = Column(UUID(as_uuid=True), ForeignKey("code_facts.id"), nullable=True)
    # [추가 - 2026.07.16] 발화가 과거 결정(decisions)과 충돌났을 때의 참조 대상.
    # 실시간 판단 파이프라인 1-1(결정 비교 판단) Case 3에서 사용.
    # 기존엔 reference_type이 content_chunk/code_fact 둘뿐이라 "결정과 충돌"을
    # 저장할 방법이 없었음 — 이 필드가 없으면 모순 해결("변경 인지함") 시
    # decisions.status를 superseded로 전이시킬 대상을 찾을 수 없어 실제로
    # 반영이 안 되는 구멍이 있었음.
    reference_decision_id = Column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=True)
    statement_text_snapshot = Column(Text, nullable=False)
    reference_text_snapshot = Column(Text, nullable=False)
    reference_location = Column(JSONB, nullable=True)
    reason = Column(Text, nullable=True)
    # [추가] decision_judgment.py Case 2/3(근거 명확/불명확) 구분 저장용.
    # reference_type='decision'인 행에서만 채워짐 - 세션 내 dedup을 case별로
    # 따로 걸기 위해 필요 (같은 decision이어도 case가 다르면 별도로 1회씩 팝업 가능).
    judgment_case = Column(String(20), nullable=True)
    confidence_score = Column(Numeric(5, 4), nullable=False)
    severity = Column(String(20), nullable=False, server_default="medium")
    deduplication_key = Column(String(64), nullable=False)
    cooldown_until = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="unresolved")
    detected_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('meeting_segment','room_message','meeting_summary')",
            name="chk_contradictions_source_type",
        ),
        CheckConstraint(
            "reference_type IN ('content_chunk','code_fact','decision')",
            name="chk_contradictions_reference_type",
        ),
        CheckConstraint("severity IN ('low','medium','high')", name="chk_contradictions_severity"),
        CheckConstraint(
            "judgment_case IS NULL OR judgment_case IN ('reasoned_change','unreasoned_change')",
            name="chk_contradictions_judgment_case",
        ),
        CheckConstraint(
            "status IN ('unresolved','resolved','dismissed')", name="chk_contradictions_status"
        ),
        CheckConstraint(
            "(source_type = 'meeting_segment' AND meeting_segment_id IS NOT NULL "
            "AND room_message_id IS NULL) OR "
            "(source_type = 'room_message' AND room_message_id IS NOT NULL "
            "AND meeting_segment_id IS NULL) OR "
            "(source_type = 'meeting_summary' AND meeting_segment_id IS NULL "
            "AND room_message_id IS NULL)",
            name="chk_contradictions_source_exclusive",
        ),
        CheckConstraint(
            "(reference_type = 'content_chunk' AND reference_chunk_id IS NOT NULL "
            "AND reference_code_fact_id IS NULL AND reference_decision_id IS NULL) OR "
            "(reference_type = 'code_fact' AND reference_code_fact_id IS NOT NULL "
            "AND reference_chunk_id IS NULL AND reference_decision_id IS NULL) OR "
            "(reference_type = 'decision' AND reference_decision_id IS NOT NULL "
            "AND reference_chunk_id IS NULL AND reference_code_fact_id IS NULL)",
            name="chk_contradictions_reference_exclusive",
        ),
        Index("idx_contradictions_workspace", "workspace_id", "status", "detected_at"),
        Index("idx_contradictions_category", "category_id", "status", "detected_at"),
        Index("idx_contradictions_reference_file", "reference_file_id", "detected_at"),
        # 세션 내 같은 decision에 이미 모순 팝업 떴는지 빠르게 조회 (1-1 Case 3, 1-5 규칙)
        Index(
            "idx_contradictions_session_decision",
            "session_meeting_id", "session_room_id", "reference_decision_id",
        ),
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