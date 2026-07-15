"""사용자 계정 / 인증"""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk
from sqlalchemy import DateTime


class User(Base):
    __tablename__ = "users"

    id = uuid_pk()
    username = Column(String(50), nullable=False)
    email = Column(String(255), nullable=False)
    display_name = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    account_status = Column(String(20), nullable=False, server_default="active")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "account_status IN ('active','inactive','locked')",
            name="chk_users_account_status",
        ),
        Index(
            "uq_users_username_active", "username", unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_users_email_active", "email", unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    device_info = Column(String(255), nullable=True)
    created_at = created_at_col()
