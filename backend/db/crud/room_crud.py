# backend/db/crud/room_crud.py

"""카테고리/채팅방/메시지 CRUD (가동현·문지수 파트 — 기본 템플릿)"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import Category, Room, RoomMessage


def create_default_category(db: Session, workspace_id: uuid.UUID, created_by: uuid.UUID) -> Category:
    """워크스페이스 생성 직후 반드시 호출. MVP: 워크스페이스당 이거 하나만 씀."""
    row = Category(
        workspace_id=workspace_id,
        name="default",
        is_default=True,
        display_order=0,
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_default_category(db: Session, workspace_id: uuid.UUID) -> Optional[Category]:
    return (
        db.query(Category)
        .filter(Category.workspace_id == workspace_id, Category.is_default.is_(True))
        .first()
    )

def get_category(db: Session, category_id: uuid.UUID) -> Optional[Category]:
    return (
        db.query(Category)
        .filter(Category.id == category_id, Category.deleted_at.is_(None))
        .first()
    )


def list_categories(db: Session, workspace_id: uuid.UUID) -> list[Category]:
    return (
        db.query(Category)
        .filter(Category.workspace_id == workspace_id, Category.deleted_at.is_(None))
        .order_by(Category.display_order.asc())
        .all()
    )


def create_category(db: Session, workspace_id: uuid.UUID, name: str, created_by: uuid.UUID) -> Category:
    max_order = (
        db.query(Category)
        .filter(Category.workspace_id == workspace_id, Category.deleted_at.is_(None))
        .count()
    )
    row = Category(
        workspace_id=workspace_id,
        name=name,
        is_default=False,
        display_order=max_order,
        created_by=created_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_category(db: Session, category_id: uuid.UUID, **fields) -> Optional[Category]:
    row = get_category(db, category_id)
    if not row:
        return None
    for k, v in fields.items():
        if v is not None:
            setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


def delete_category(db: Session, category_id: uuid.UUID) -> Optional[Category]:
    row = get_category(db, category_id)
    if row:
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


def create_room(db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, name: str, created_by: uuid.UUID) -> Room:
    row = Room(workspace_id=workspace_id, category_id=category_id, name=name, created_by=created_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_rooms(db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID | None = None) -> list[Room]:
    query = db.query(Room).filter(Room.workspace_id == workspace_id, Room.deleted_at.is_(None))
    if category_id is not None:
        query = query.filter(Room.category_id == category_id)
    return query.all()

def get_room_by_id(db: Session, room_id: uuid.UUID, workspace_id: uuid.UUID) -> Optional[Room]:
    return (
        db.query(Room)
        .filter(
            Room.id == room_id,
            Room.workspace_id == workspace_id,
            Room.deleted_at.is_(None),
        )
        .first()
    )


def update_room(db: Session, room_id: uuid.UUID, **fields) -> Optional[Room]:
    row = db.query(Room).filter(Room.id == room_id, Room.deleted_at.is_(None)).first()
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
    return row


def delete_room(db: Session, room_id: uuid.UUID) -> Optional[Room]:
    row = db.query(Room).filter(Room.id == room_id, Room.deleted_at.is_(None)).first()
    if row:
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


def add_message(db: Session, room_id: uuid.UUID, message_type: str, content: str, sender_user_id: Optional[uuid.UUID] = None, **fields) -> RoomMessage:
    """message_type='ai_summary'/'system'이면 sender_user_id=None 허용."""
    row = RoomMessage(
        room_id=room_id, message_type=message_type, content=content, sender_user_id=sender_user_id, **fields
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_recent_messages(db: Session, room_id: uuid.UUID, limit: int = 50) -> list[RoomMessage]:
    return (
        db.query(RoomMessage)
        .filter(RoomMessage.room_id == room_id, RoomMessage.deleted_at.is_(None))
        .order_by(RoomMessage.created_at.desc())
        .limit(limit)
        .all()
    )


def get_message_by_id(db: Session, message_id: uuid.UUID) -> Optional[RoomMessage]:
    return (
        db.query(RoomMessage)
        .filter(RoomMessage.id == message_id, RoomMessage.deleted_at.is_(None))
        .first()
    )


def delete_message(db: Session, message_id: uuid.UUID) -> Optional[RoomMessage]:
    row = db.query(RoomMessage).filter(
        RoomMessage.id == message_id, RoomMessage.deleted_at.is_(None)
    ).first()
    if row:
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row