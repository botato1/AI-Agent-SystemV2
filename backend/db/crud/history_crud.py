"""관련 이력 리마인더(결정 리마인더/문서 추천/반복 논의) CRUD — 내 파트"""

import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.modules import RelatedHistoryMatch


def already_notified_in_session(
    db: Session,
    *,
    session_meeting_id: Optional[uuid.UUID] = None,
    session_room_id: Optional[uuid.UUID] = None,
    reference_decision_id: Optional[uuid.UUID] = None,
    reference_file_id: Optional[uuid.UUID] = None,
) -> bool:
    """
    3-1(결정 리마인더)/3-2(문서 추천)의 "세션당 1회" 체크.
    session_meeting_id 또는 session_room_id 중 발화 출처에 맞는 쪽 하나만 넘길 것.
    """
    q = db.query(RelatedHistoryMatch)
    if session_meeting_id:
        q = q.filter(RelatedHistoryMatch.session_meeting_id == session_meeting_id)
    if session_room_id:
        q = q.filter(RelatedHistoryMatch.session_room_id == session_room_id)
    if reference_decision_id:
        q = q.filter(RelatedHistoryMatch.reference_decision_id == reference_decision_id)
    if reference_file_id:
        q = q.filter(RelatedHistoryMatch.reference_file_id == reference_file_id)
    return db.query(q.exists()).scalar()


def record_match(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    source_type: str,
    match_type: str,
    session_meeting_id: Optional[uuid.UUID] = None,
    session_room_id: Optional[uuid.UUID] = None,
    reference_decision_id: Optional[uuid.UUID] = None,
    reference_file_id: Optional[uuid.UUID] = None,
    confidence_score: Optional[float] = None,
    **extra_fields,
) -> RelatedHistoryMatch:
    """
    알림을 실제로 띄운 시점에 호출 — "이미 알림 줬다"는 기록을 남기는 함수.
    already_notified_in_session()으로 먼저 확인 후, 처음이면 팝업 띄우고 이 함수 호출.
    """
    row = RelatedHistoryMatch(
        workspace_id=workspace_id,
        category_id=category_id,
        source_type=source_type,
        match_type=match_type,
        session_meeting_id=session_meeting_id,
        session_room_id=session_room_id,
        reference_decision_id=reference_decision_id,
        reference_file_id=reference_file_id,
        confidence_score=confidence_score,
        **extra_fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def count_repeat_sessions(db: Session, category_id: uuid.UUID, decision_id: uuid.UUID) -> int:
    """
    3-3(반복 논의 알림)용 — 같은 decision_id가 서로 다른 세션(회의/채팅방)에
    걸쳐 몇 번 매칭됐는지 센다. meeting/room 어느 쪽이든 세션 하나로 취급.
    """
    meeting_sessions = (
        db.query(RelatedHistoryMatch.session_meeting_id)
        .filter(
            RelatedHistoryMatch.category_id == category_id,
            RelatedHistoryMatch.reference_decision_id == decision_id,
            RelatedHistoryMatch.session_meeting_id.isnot(None),
        )
        .distinct()
        .count()
    )
    room_sessions = (
        db.query(RelatedHistoryMatch.session_room_id)
        .filter(
            RelatedHistoryMatch.category_id == category_id,
            RelatedHistoryMatch.reference_decision_id == decision_id,
            RelatedHistoryMatch.session_room_id.isnot(None),
        )
        .distinct()
        .count()
    )
    return meeting_sessions + room_sessions