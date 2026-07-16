"""회의/결정/할일 CRUD (가동현 파트 — 기본 템플릿)"""

import uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.modules import Task, Decision, Meeting, MeetingSegment, MeetingSummary


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

def get_meeting(db: Session, meeting_id: uuid.UUID) -> Optional[Meeting]:
    return (
        db.query(Meeting)
        .filter(Meeting.id == meeting_id, Meeting.deleted_at.is_(None))
        .first()
    )


def list_meetings(db: Session, workspace_id: uuid.UUID) -> list[Meeting]:
    return (
        db.query(Meeting)
        .filter(Meeting.workspace_id == workspace_id, Meeting.deleted_at.is_(None))
        .order_by(Meeting.created_at.desc())
        .all()
    )


def update_meeting_status(db: Session, meeting_id: uuid.UUID, status: str, **fields) -> Optional[Meeting]:
    row = get_meeting(db, meeting_id)
    if row:
        row.status = status
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
    return row


def delete_meeting(db: Session, meeting_id: uuid.UUID) -> Optional[Meeting]:
    row = get_meeting(db, meeting_id)
    if row:
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


def get_meeting_summary(db: Session, meeting_id: uuid.UUID) -> Optional[MeetingSummary]:
    return db.query(MeetingSummary).filter(MeetingSummary.meeting_id == meeting_id).first()


def list_decisions_by_meeting(db: Session, meeting_id: uuid.UUID) -> list[Decision]:
    return (
        db.query(Decision)
        .filter(Decision.meeting_id == meeting_id, Decision.deleted_at.is_(None))
        .order_by(Decision.decided_at.desc())
        .all()
    )


def create_task(db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, title: str, **fields) -> Task:
    row = Task(workspace_id=workspace_id, category_id=category_id, title=title, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_open_tasks(db: Session, workspace_id: uuid.UUID) -> list[Task]:
    return (
        db.query(Task)
        .filter(
            Task.workspace_id == workspace_id,
            Task.status.in_(["open", "in_progress"]),
            Task.deleted_at.is_(None),
        )
        .all()
    )


def list_open_tasks_by_category(db: Session, category_id: uuid.UUID) -> list[Task]:
    """대시보드(카테고리 단위) 담당자별 할 일 요약용."""
    return (
        db.query(Task)
        .filter(
            Task.category_id == category_id,
            Task.status.in_(["open", "in_progress"]),
            Task.deleted_at.is_(None),
        )
        .all()
    )

def get_task(db: Session, task_id: uuid.UUID) -> Optional[Task]:
    return (
        db.query(Task)
        .filter(Task.id == task_id, Task.deleted_at.is_(None))
        .first()
    )


def update_task_status(db: Session, task_id: uuid.UUID, status: str) -> Optional[Task]:
    row = get_task(db, task_id)
    if row:
        row.status = status
        if status == "done":
            row.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


def update_task_priority(db: Session, task_id: uuid.UUID, priority: str) -> Optional[Task]:
    row = get_task(db, task_id)
    if row:
        row.priority = priority
        db.commit()
        db.refresh(row)
    return row


def delete_task(db: Session, task_id: uuid.UUID) -> Optional[Task]:
    row = get_task(db, task_id)
    if row:
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row