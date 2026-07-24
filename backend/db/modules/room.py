"""카테고리(MVP 백엔드 전용) / 채팅방 / 채팅 메시지"""

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, text,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class Category(Base):
    """MVP: 프론트엔드 미표시. 워크스페이스 생성 시 is_default=true 1개 자동 생성."""

    __tablename__ = "categories"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, nullable=False, server_default="false")
    display_order = Column(Integer, nullable=False, server_default="0")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class Room(Base):
    """rag_enabled 없음 — 채팅은 RAG 소스가 아님."""

    __tablename__ = "rooms"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    name = Column(String(100), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_rooms_workspace", "workspace_id", "category_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class RoomMessage(Base):
    """모순 감지 대상이지만 RAG 소스로 ChromaDB에 저장하지 않음."""

    __tablename__ = "room_messages"

    id = uuid_pk()
    room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False)
    sender_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    message_type = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    reply_to_id = Column(UUID(as_uuid=True), ForeignKey("room_messages.id"), nullable=True)
    is_edited = Column(Boolean, nullable=False, server_default="false")
    edited_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "message_type IN ('text','file','ai_summary','contradiction_alert',"
            "'meeting_notice','system')",
            name="chk_room_messages_type",
        ),
        Index(
            "idx_room_messages_room", "room_id", "created_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
