"""워크스페이스 / 멤버"""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class Workspace(Base):
    __tablename__ = "workspaces"

    id = uuid_pk()
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False, server_default="member")
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    joined_at = created_at_col()
    removed_at = Column(DateTime(timezone=True), nullable=True)
    notification_preferences = Column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
        CheckConstraint("role IN ('owner','member')", name="chk_workspace_member_role"),
        Index("idx_workspace_members_user", "user_id", "workspace_id"),
        Index("idx_workspace_members_workspace", "workspace_id", "role"),
    )
