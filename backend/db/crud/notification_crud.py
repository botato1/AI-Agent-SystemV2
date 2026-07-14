"""알림 CRUD (문지수 파트 — 기본 템플릿)"""

import uuid

from sqlalchemy.orm import Session

from backend.db.modules import Notification


def create_notification(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID, type: str, **fields) -> Notification:
    row = Notification(user_id=user_id, workspace_id=workspace_id, type=type, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_unread(db: Session, user_id: uuid.UUID) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .order_by(Notification.created_at.desc())
        .all()
    )


def mark_read(db: Session, notification_id: uuid.UUID) -> None:
    from sqlalchemy import func
    row = db.query(Notification).filter(Notification.id == notification_id).first()
    if row:
        row.is_read = True
        row.read_at = func.now()
        db.commit()
