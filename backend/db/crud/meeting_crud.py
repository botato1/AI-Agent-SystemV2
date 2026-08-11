"""회의/결정/할일 CRUD"""

import uuid
from typing import Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
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
        .order_by(MeetingSegment.start_ms, MeetingSegment.segment_index)
        .all()
    )

def update_segment_content(
    db: Session, segment_id: uuid.UUID,
    content: Optional[str] = None, speaker_label: Optional[str] = None,
) -> Optional[MeetingSegment]:
    segment = db.get(MeetingSegment, segment_id)
    if not segment:
        return None
    if content is not None:
        segment.content = content
    if speaker_label is not None:
        segment.speaker_label = speaker_label
    segment.is_edited = True
    db.commit()
    db.refresh(segment)
    return segment

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

def list_suggested_tasks_by_meeting(db: Session, meeting_id: uuid.UUID) -> list[Task]:
    return (
        db.query(Task)
        .filter(
            Task.meeting_id == meeting_id,
            Task.status == "suggested",
            Task.deleted_at.is_(None),
        )
        .all()
    )


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

def list_tasks(db: Session, workspace_id: uuid.UUID, include_done: bool = False) -> list[Task]:
    """워크스페이스의 할 일 목록을 조회한다.
    include_done=False(기본)면 open/in_progress만, True면 done/cancelled/suggested까지 전부 포함."""
    query = db.query(Task).filter(
        Task.workspace_id == workspace_id,
        Task.deleted_at.is_(None),
    )
    if not include_done:
        query = query.filter(Task.status.in_(["open", "in_progress"]))
    return query.all()


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
    """참석자 목록을 통째로 교체한다. 회의 시작자는 프론트가 보낸 목록에 없어도 항상 포함되고
    is_initial=True로 표시된다 (시작자 본인이 자동 등록 안 되던 버그 수정)."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    started_by = meeting.started_by if meeting else None

    final_ids = set(user_ids)
    if started_by:
        final_ids.add(started_by)

    db.query(MeetingAttendee).filter(MeetingAttendee.meeting_id == meeting_id).delete(synchronize_session=False)
    db.add_all([
        MeetingAttendee(meeting_id=meeting_id, user_id=uid, is_initial=(uid == started_by))
        for uid in final_ids
    ])
    db.commit()
    return get_attendees(db, meeting_id)


def get_attendees(db: Session, meeting_id: uuid.UUID) -> list[tuple[MeetingAttendee, User]]:
    return (
        db.query(MeetingAttendee, User)
        .join(User, MeetingAttendee.user_id == User.id)
        .filter(MeetingAttendee.meeting_id == meeting_id)
        .all()
    )

def get_segment(db: Session, segment_id: uuid.UUID) -> Optional[MeetingSegment]:
    return db.query(MeetingSegment).filter(MeetingSegment.id == segment_id).first()

def list_recent_meetings(db: Session, workspace_id: uuid.UUID, limit: int = 10) -> list[Meeting]:
    return (
        db.query(Meeting)
        .filter(Meeting.workspace_id == workspace_id, Meeting.deleted_at.is_(None))
        .order_by(Meeting.created_at.desc())
        .limit(limit)
        .all()
    )


def count_meetings(db: Session, workspace_id: uuid.UUID) -> int:
    return (
        db.query(Meeting)
        .filter(Meeting.workspace_id == workspace_id, Meeting.deleted_at.is_(None))
        .count()
    )

def get_last_meeting_at(db: Session, workspace_id: uuid.UUID) -> Optional[datetime]:
    row = (
        db.query(Meeting)
        .filter(
            Meeting.workspace_id == workspace_id,
            Meeting.deleted_at.is_(None),
            Meeting.started_at.isnot(None),
        )
        .order_by(Meeting.started_at.desc())
        .first()
    )
    return row.started_at if row else None


def get_week_meeting_stats(db: Session, workspace_id: uuid.UUID, week_start: datetime, week_end: datetime) -> dict:
    meetings = (
        db.query(Meeting)
        .filter(
            Meeting.workspace_id == workspace_id,
            Meeting.deleted_at.is_(None),
            Meeting.started_at >= week_start,
            Meeting.started_at < week_end,
        )
        .all()
    )
    return {
        "count": len(meetings),
        "duration_ms": sum(m.duration_ms or 0 for m in meetings),
    }

def get_meeting_by_source_file_id(db: Session, file_id: uuid.UUID) -> Optional[Meeting]:
    """RAG 검색 결과(청크의 file_id)로 그 회의를 역추적할 때 사용."""
    return (
        db.query(Meeting)
        .filter(Meeting.source_file_id == file_id, Meeting.deleted_at.is_(None))
        .first()
    )


def search_meetings_by_text(db: Session, workspace_id: uuid.UUID, q: str) -> list[Meeting]:
    """제목/주제/요약에 대한 단순 텍스트 매칭."""
    pattern = f"%{q}%"
    return (
        db.query(Meeting)
        .outerjoin(MeetingSummary, MeetingSummary.meeting_id == Meeting.id)
        .filter(
            Meeting.workspace_id == workspace_id,
            Meeting.deleted_at.is_(None),
            or_(
                Meeting.title.ilike(pattern),
                Meeting.topic.ilike(pattern),
                MeetingSummary.short_summary.ilike(pattern),
            ),
        )
        .all()
    )


def list_meetings_by_date_range(
    db: Session, workspace_id: uuid.UUID,
    date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
) -> list[Meeting]:
    query = db.query(Meeting).filter(Meeting.workspace_id == workspace_id, Meeting.deleted_at.is_(None))
    if date_from:
        query = query.filter(Meeting.started_at >= date_from)
    if date_to:
        query = query.filter(Meeting.started_at <= date_to)
    return query.order_by(Meeting.started_at.desc()).all()


def list_upcoming_meetings(db: Session, workspace_id: uuid.UUID) -> list[Meeting]:
    return (
        db.query(Meeting)
        .filter(
            Meeting.workspace_id == workspace_id,
            Meeting.deleted_at.is_(None),
            Meeting.status == "scheduled",
        )
        .order_by(Meeting.scheduled_at.asc())
        .all()
    )

def add_segment_safe(db: Session, meeting_id: uuid.UUID, content: str, start_ms: int, end_ms: int, **fields) -> MeetingSegment:
    """여러 WS 연결이 동시에 세그먼트를 저장해도(각자 PC 모드) segment_index 충돌 없이 삽입한다.
    충돌 시 최대 5회 재시도."""
    for _ in range(5):
        current_max = (
            db.query(func.max(MeetingSegment.segment_index))
            .filter(MeetingSegment.meeting_id == meeting_id)
            .scalar()
        )
        next_index = (current_max + 1) if current_max is not None else 0
        try:
            row = MeetingSegment(
                meeting_id=meeting_id, content=content, start_ms=start_ms, end_ms=end_ms,
                segment_index=next_index, **fields,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row
        except IntegrityError:
            db.rollback()
            continue
    raise RuntimeError(f"세그먼트 저장 재시도 초과 (meeting_id={meeting_id})")

def split_segment(
    db: Session, segment_id: uuid.UUID,
    first_content: str, second_content: str,
    first_speaker_label: str | None = None,
    second_speaker_label: str | None = None,
) -> Optional[tuple[MeetingSegment, MeetingSegment]]:
    segment = db.get(MeetingSegment, segment_id)
    if not segment:
        return None

    start_ms, end_ms = segment.start_ms, segment.end_ms
    midpoint_ms = start_ms + (end_ms - start_ms) // 2
    midpoint_ms = max(start_ms + 1, min(midpoint_ms, end_ms - 1))

    for _ in range(5):
        # rollback되면 세션 객체가 expire되므로, segment 변경도 매 시도마다 다시 적용한다.
        segment.content = first_content
        segment.end_ms = midpoint_ms
        if first_speaker_label is not None:
            segment.speaker_label = first_speaker_label
        segment.is_edited = True

        current_max = (
            db.query(func.max(MeetingSegment.segment_index))
            .filter(MeetingSegment.meeting_id == segment.meeting_id)
            .scalar()
        )
        next_index = (current_max or 0) + 1
        second = MeetingSegment(
            meeting_id=segment.meeting_id,
            speaker_label=second_speaker_label,
            content=second_content,
            start_ms=midpoint_ms,
            end_ms=end_ms,
            segment_index=next_index,
            is_edited=True,
        )
        db.add(second)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(segment)
        db.refresh(second)
        return segment, second
    raise RuntimeError(f"세그먼트 분할 재시도 초과 (meeting_id={segment.meeting_id})")

def get_decision(db: Session, decision_id: uuid.UUID) -> Optional[Decision]:
    return db.query(Decision).filter(Decision.id == decision_id, Decision.deleted_at.is_(None)).first()


def update_decision(db: Session, decision_id: uuid.UUID, **fields) -> Optional[Decision]:
    row = get_decision(db, decision_id)
    if not row:
        return None
    for key, value in fields.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row

def list_meetings_needing_reminder(db: Session, reminder_minutes: int) -> list[Meeting]:
    """지금부터 reminder_minutes 이내에 시작하는 예약 회의 목록."""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=reminder_minutes)
    return (
        db.query(Meeting)
        .filter(
            Meeting.deleted_at.is_(None),
            Meeting.status == "scheduled",
            Meeting.scheduled_at > now,
            Meeting.scheduled_at <= window_end,
        )
        .all()
    )