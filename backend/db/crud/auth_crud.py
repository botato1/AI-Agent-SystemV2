# backend/db/crud/auth_crud.py

"""인증/사용자 CRUD (문지수 파트 — 기본 템플릿, 필요 시 확장)"""

import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.modules import RefreshToken, User, UserVoiceProfile


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


def update_user_profile(db: Session, user_id: uuid.UUID, **fields) -> Optional[User]:
    row = get_user_by_id(db, user_id)
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
    return row


def update_user_password(db: Session, user_id: uuid.UUID, password_hash: str) -> Optional[User]:
    return update_user_profile(db, user_id, password_hash=password_hash)


def update_user_last_login(db: Session, user_id: uuid.UUID) -> Optional[User]:
    return update_user_profile(db, user_id, last_login_at=func.now())


def store_refresh_token(db: Session, **fields) -> RefreshToken:
    row = RefreshToken(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_refresh_token_by_hash(db: Session, token_hash: str) -> Optional[RefreshToken]:
    return db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()


def revoke_refresh_token(db: Session, token_hash: str) -> None:
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if row:
        row.revoked_at = func.now()
        db.commit()

def soft_delete_user(db: Session, user_id: uuid.UUID) -> Optional[User]:
    row = get_user_by_id(db, user_id)
    if row:
        row.deleted_at = func.now()
        row.account_status = "inactive"
        db.commit()
        db.refresh(row)
    return row


def revoke_all_refresh_tokens_for_user(db: Session, user_id: uuid.UUID) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    ).update({RefreshToken.revoked_at: func.now()})
    db.commit()

def get_voice_profile(db: Session, user_id: uuid.UUID) -> Optional[UserVoiceProfile]:
    return db.query(UserVoiceProfile).filter(UserVoiceProfile.user_id == user_id).first()


def create_voice_profile(
    db: Session, user_id: uuid.UUID, speaker_name: str, detected_text: Optional[str] = None,
) -> UserVoiceProfile:
    row = UserVoiceProfile(user_id=user_id, speaker_name=speaker_name, detected_text=detected_text)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_voice_profile_speaker_name(db: Session, user_id: uuid.UUID, speaker_name: str) -> Optional[UserVoiceProfile]:
    row = get_voice_profile(db, user_id)
    if row:
        row.speaker_name = speaker_name
        db.commit()
        db.refresh(row)
    return row


def delete_voice_profile(db: Session, user_id: uuid.UUID) -> Optional[UserVoiceProfile]:
    row = get_voice_profile(db, user_id)
    if row:
        db.delete(row)
        db.commit()
    return row