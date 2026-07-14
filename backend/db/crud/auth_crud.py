"""인증/사용자 CRUD (문지수 파트 — 기본 템플릿, 필요 시 확장)"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import RefreshToken, User


def create_user(db: Session, **fields) -> User:
    row = User(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_user_by_id(db: Session, user_id: uuid.UUID) -> Optional[User]:
    return db.query(User).filter(User.id == user_id, User.deleted_at.is_(None)).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return (
        db.query(User)
        .filter(User.username == username, User.deleted_at.is_(None))
        .first()
    )


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first()


def store_refresh_token(db: Session, **fields) -> RefreshToken:
    row = RefreshToken(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revoke_refresh_token(db: Session, token_hash: str) -> None:
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if row:
        from sqlalchemy import func
        row.revoked_at = func.now()
        db.commit()
