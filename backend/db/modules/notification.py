"""알림"""

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, uuid_pk


class Notification(Base):
    __tablename__ = "notifications"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    type = Column(String(40), nullable=False)
    title = Column(String(200), nullable=True)
    message = Column(Text, nullable=True)
    ref_type = Column(String(30), nullable=True)
    ref_id = Column(UUID(as_uuid=True), nullable=True)
    related_file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=True)  # document_recommendation 등에서 사용
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=True)
    is_read = Column(Boolean, nullable=False, server_default="false")
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "type IN ('contradiction_detected','contradiction_resolved',"
            "'meeting_summary_ready','file_analysis_completed','file_analysis_failed',"
            "'decision_reminder','repeat_discussion','document_recommendation',"
            "'meeting_reminder')",
            name="chk_notifications_type",
        ),
        Index(
            "idx_notifications_unread", "user_id", "is_read", "created_at",
            postgresql_where=text("is_read = false"),
        ),
    )
