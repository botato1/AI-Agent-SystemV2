"""알림 CRUD (문지수 파트 — 기본 템플릿)"""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.modules import Notification


def create_notification(db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID, type: str, commit: bool = True, **fields) -> Notification:
    row = Notification(user_id=user_id, workspace_id=workspace_id, type=type, **fields)
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def list_notifications(
    db: Session, user_id: uuid.UUID, workspace_id: uuid.UUID, unread_only: bool = False,
) -> list[Notification]:
    q = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.workspace_id == workspace_id,
    )
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    return q.order_by(Notification.created_at.desc()).all()


def get_notification(db: Session, notification_id: uuid.UUID) -> Notification | None:
    return db.query(Notification).filter(Notification.id == notification_id).first()


def mark_read(db: Session, notification_id: uuid.UUID) -> None:
    row = db.query(Notification).filter(Notification.id == notification_id).first()
    if row:
        row.is_read = True
        row.read_at = func.now()
        db.commit()