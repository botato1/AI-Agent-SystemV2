"""회의/결정/할일 CRUD (가동현 파트 — 기본 템플릿)"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import ActionItem, Decision, Meeting, MeetingSegment, MeetingSummary


def create_meeting(
    db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, title: str,
    input_type: str, started_by: uuid.UUID, **fields,
) -> Meeting:
    """category_id: 회의가 저장될 카테고리. MVP에서는 room_crud.get_default_category() 결과를 그대로 넣으면 됨."""
    row = Meeting(
        workspace_id=workspace_id, category_id=category_id, title=title,
        input_type=input_type, started_by=started_by, **fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_segment(db: Session, meeting_id: uuid.UUID, content: str, start_ms: int, end_ms: int, segment_index: int, **fields) -> MeetingSegment:
    row = MeetingSegment(
        meeting_id=meeting_id, content=content, start_ms=start_ms, end_ms=end_ms,
        segment_index=segment_index, **fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_segments(db: Session, meeting_id: uuid.UUID) -> list[MeetingSegment]:
    return (
        db.query(MeetingSegment)
        .filter(MeetingSegment.meeting_id == meeting_id)
        .order_by(MeetingSegment.segment_index)
        .all()
    )


def upsert_summary(db: Session, meeting_id: uuid.UUID, **fields) -> MeetingSummary:
    row = db.query(MeetingSummary).filter(MeetingSummary.meeting_id == meeting_id).first()
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
    else:
        row = MeetingSummary(meeting_id=meeting_id, **fields)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_decision(db: Session, workspace_id: uuid.UUID, meeting_id: uuid.UUID, title: str, decision_text: str, decided_at, **fields) -> Decision:
    """MVP: post-meeting 일괄 추출로만 호출됨 (실시간 채팅에서는 호출 안 함)."""
    row = Decision(
        workspace_id=workspace_id, meeting_id=meeting_id, title=title,
        decision_text=decision_text, decided_at=decided_at, **fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_action_item(db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, title: str, **fields) -> ActionItem:
    row = ActionItem(workspace_id=workspace_id, category_id=category_id, title=title, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_open_action_items(db: Session, workspace_id: uuid.UUID) -> list[ActionItem]:
    return (
        db.query(ActionItem)
        .filter(
            ActionItem.workspace_id == workspace_id,
            ActionItem.status.in_(["open", "in_progress"]),
            ActionItem.deleted_at.is_(None),
        )
        .all()
    )


def list_open_action_items_by_category(db: Session, category_id: uuid.UUID) -> list[ActionItem]:
    """대시보드(카테고리 단위) 담당자별 할 일 요약용."""
    return (
        db.query(ActionItem)
        .filter(
            ActionItem.category_id == category_id,
            ActionItem.status.in_(["open", "in_progress"]),
            ActionItem.deleted_at.is_(None),
        )
        .all()
    )