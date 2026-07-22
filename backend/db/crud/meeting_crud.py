"""회의/결정/할일 CRUD (가동현 파트 — 기본 템플릿)"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import Decision, Meeting, MeetingSegment, MeetingSummary, Task


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


def upsert_summary(db: Session, meeting_id: uuid.UUID, commit: bool = True, **fields) -> MeetingSummary:
    """
    [수정 - 리뷰 반영 9번] commit 옵션 추가. post_meeting.pipeline.run()처럼
    여러 CRUD 호출을 하나의 트랜잭션으로 묶어서 실패 시 전체 rollback이
    실제로 동작하게 하려면 commit=False로 호출하고, 호출부(pipeline)가
    마지막에 한 번만 commit해야 한다. 기본값 True라 기존 호출부는 그대로 동작.
    """
    row = db.query(MeetingSummary).filter(MeetingSummary.meeting_id == meeting_id).first()
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
    else:
        row = MeetingSummary(meeting_id=meeting_id, **fields)
        db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
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


# [수정 - 리뷰 반영] ActionItem -> Task 팀 컨벤션으로 모델/함수명 전면 변경.
# 기존 create_action_item/list_open_action_items_by_category는 삭제하고
# create_task/list_open_tasks_by_category로 완전히 대체 (wrapper 아님).
def create_task(db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, title: str, commit: bool = True, **fields) -> Task:
    row = Task(workspace_id=workspace_id, category_id=category_id, title=title, **fields)
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
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