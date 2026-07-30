"""알림 CRUD (문지수 파트 — 기본 템플릿)"""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.modules import Notification, WorkspaceMember

_DEFAULT_PREFERENCES = {"new_message": True, "meeting_summary": True, "contradiction": True}

# 실제로 생성되는 알림 타입만 매핑. 여기 없는 타입은 항상 발송(그룹 없음 취급).
# meeting_summary_ready/contradiction_detected/contradiction_resolved은 아직
# 어떤 코드도 생성하지 않아서 매핑해도 당장은 효과 없음 — 생성 코드 생기면 추가할 것.
_TYPE_TO_GROUP = {
    "meeting_summary_ready": "meeting_summary",
    "contradiction_detected": "contradiction",
    "contradiction_resolved": "contradiction",
}


def _get_member(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceMember | None:
    return (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .first()
    )


def get_notification_preferences(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    member = _get_member(db, workspace_id, user_id)
    stored = (member.notification_preferences if member else None) or {}
    return {**_DEFAULT_PREFERENCES, **stored}


def update_notification_preferences(
    db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, updates: dict,
) -> dict:
    member = _get_member(db, workspace_id, user_id)
    current = {**_DEFAULT_PREFERENCES, **(member.notification_preferences or {} if member else {})}
    current.update({k: v for k, v in updates.items() if v is not None})
    if member:
        member.notification_preferences = current
        db.commit()
    return current


def is_notification_enabled(
    db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, notification_type: str,
) -> bool:
    group = _TYPE_TO_GROUP.get(notification_type)
    if group is None:
        return True
    return get_notification_preferences(db, workspace_id, user_id).get(group, True)


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