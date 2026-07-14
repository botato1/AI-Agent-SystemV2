"""AI Chat (채팅방 단위 개인 RAG QA) — 내 파트"""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class AiChatSession(Base):
    """채팅방(room) 안에 존재. 기록은 사용자별 비공개."""

    __tablename__ = "ai_chat_sessions"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(200), nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_ai_chat_sessions_owner", "workspace_id", "room_id", "user_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class AiChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id = uuid_pk()
    session_id = Column(UUID(as_uuid=True), ForeignKey("ai_chat_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    model_name = Column(String(100), nullable=True)
    created_at = created_at_col()

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="chk_ai_chat_messages_role"),
    )


class AiMessageSource(Base):
    """AI 답변 근거. source_type에 따라 chunk_id 또는 code_fact_id 중 하나만 채운다."""

    __tablename__ = "ai_message_sources"

    id = uuid_pk()
    ai_message_id = Column(UUID(as_uuid=True), ForeignKey("ai_chat_messages.id"), nullable=False)
    source_type = Column(String(30), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("content_chunks.id"), nullable=True)
    code_fact_id = Column(UUID(as_uuid=True), ForeignKey("code_facts.id"), nullable=True)
    similarity_score = Column(Numeric(5, 4), nullable=True)
    display_order = Column(Integer, nullable=False, server_default="0")
    created_at = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('content_chunk','code_fact')", name="chk_ai_message_sources_type"
        ),
        CheckConstraint(
            "(source_type = 'content_chunk' AND chunk_id IS NOT NULL AND code_fact_id IS NULL) OR "
            "(source_type = 'code_fact' AND code_fact_id IS NOT NULL AND chunk_id IS NULL)",
            name="chk_ai_message_sources_exclusive",
        ),
        Index("idx_ai_message_sources_message", "ai_message_id", "display_order"),
    )
