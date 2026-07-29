"""회의/결정/할일 CRUD"""

import uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.modules import Task, Decision, Meeting, MeetingAttendee, MeetingSegment, MeetingSummary, User


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


def add_segments_bulk(db: Session, meeting_id: uuid.UUID, segments: list[dict]) -> list[MeetingSegment]:
    """세그먼트를 한 번에 저장(단일 commit). STT 스트리밍 종료 후 일괄 저장할 때 사용."""
    rows = [MeetingSegment(meeting_id=meeting_id, **seg) for seg in segments]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


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

def update_summary_file(db: Session, meeting_id: uuid.UUID, file_id: uuid.UUID) -> Optional[MeetingSummary]:
    """요약이 문서(workspace_files)로 저장된 뒤, 그 file_id를 요약 레코드에 연결한다."""
    row = get_meeting_summary(db, meeting_id)
    if row:
        row.file_id = file_id
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

def update_meeting_info(db: Session, meeting_id: uuid.UUID, **fields) -> Optional[Meeting]:
    row = get_meeting(db, meeting_id)
    if row:
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
    return row

def try_transition_meeting_status(
    db: Session, meeting_id: uuid.UUID, from_status: str, to_status: str, **fields,
) -> Optional[Meeting]:
    """from_status일 때만 to_status로 전이하는 원자적 업데이트.

    REST /end와 WS 종료가 동시에 들어와도 둘 다 read-then-write를 하면
    양쪽 다 전이에 성공했다고 착각해 후처리가 중복 실행될 수 있다.
    UPDATE ... WHERE status=from_status로 실제 전이한 쪽만 True(row 반환)가 되게 한다.
    """
    updated_rows = (
        db.query(Meeting)
        .filter(
            Meeting.id == meeting_id,
            Meeting.deleted_at.is_(None),
            Meeting.status == from_status,
        )
        .update({"status": to_status, **fields}, synchronize_session=False)
    )
    db.commit()
    if updated_rows == 0:
        return None
    return get_meeting(db, meeting_id)


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

def list_decisions_by_workspace(db: Session, workspace_id: uuid.UUID, status: str | None = None) -> list[Decision]:
    query = db.query(Decision).filter(Decision.workspace_id == workspace_id, Decision.deleted_at.is_(None))
    query = query.filter(Decision.status == (status or "active"))
    return query.order_by(Decision.decided_at.desc()).all()


def get_decision_history_chain(db: Session, decision_id: uuid.UUID) -> list[Decision]:
    """supersedes_decision_id를 따라가며 이 결정의 전체 버전 이력을 모은다.
    (최신 -> 과거 순, 현재 버전도 포함)"""
    chain: list[Decision] = []
    current = db.get(Decision, decision_id)
    while current:
        chain.append(current)
        current = db.get(Decision, current.supersedes_decision_id) if current.supersedes_decision_id else None
    return chain


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

def update_task(db: Session, task_id: uuid.UUID, **fields) -> Optional[Task]:
    """전달된 필드만 갱신한다. status가 'done'으로 바뀌면 completed_at도 함께 채운다."""
    row = get_task(db, task_id)
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        if fields.get("status") == "done":
            row.completed_at = datetime.now(timezone.utc)
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

def update_speaker_labels(db: Session, meeting_id: uuid.UUID, mapping: dict[str, str]) -> Optional[Meeting]:
    """화자 라벨(SPEAKER_00 등)을 실명으로 매핑한다.
    - meetings.speaker_labels에 매핑을 누적 저장 (이후 실시간 세그먼트에도 적용하기 위함)
    - 이미 저장된 세그먼트 중 매핑 대상 라벨을 가진 것들은 실명으로 소급 변경한다.
    """
    meeting = get_meeting(db, meeting_id)
    if not meeting:
        return None

    existing = dict(meeting.speaker_labels or {})
    existing.update(mapping)
    meeting.speaker_labels = existing

    for raw_label, display_name in mapping.items():
        db.query(MeetingSegment).filter(
            MeetingSegment.meeting_id == meeting_id,
            MeetingSegment.speaker_label == raw_label,
        ).update({"speaker_label": display_name}, synchronize_session=False)

    db.commit()
    db.refresh(meeting)
    return meeting

def set_attendees(db: Session, meeting_id: uuid.UUID, user_ids: list[uuid.UUID]) -> list[tuple[MeetingAttendee, User]]:
    """참석자 목록을 통째로 교체한다."""
    db.query(MeetingAttendee).filter(MeetingAttendee.meeting_id == meeting_id).delete(synchronize_session=False)
    db.add_all([MeetingAttendee(meeting_id=meeting_id, user_id=uid) for uid in user_ids])
    db.commit()
    return get_attendees(db, meeting_id)


def get_attendees(db: Session, meeting_id: uuid.UUID) -> list[tuple[MeetingAttendee, User]]:
    return (
        db.query(MeetingAttendee, User)
        .join(User, MeetingAttendee.user_id == User.id)
        .filter(MeetingAttendee.meeting_id == meeting_id)
        .all()
    )