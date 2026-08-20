"""관련 이력 리마인더 매칭 로그 — 내 파트

결정 리마인더 / 문서·코드 추천 / 반복 논의 알림, 세 기능이 공유하는 테이블.
모순(Contradiction)과 달리 "참고 정보" 성격이라 별도로 분리했다.

이 테이블 하나로 두 가지를 동시에 해결한다:
1. "세션당 1회" 중복 방지: 같은 세션(room 또는 meeting) 안에서 같은 참조
   대상(decision/file)에 대해 이미 알림을 줬는지 체크
2. "반복 논의" 카운트: 같은 decision_id가 서로 다른 세션에 걸쳐 몇 번
   매칭됐는지 세어서 임계치 넘으면 반복 논의 알림으로 격상

세션 스코프 정의:
  source_type = room_message    -> 세션 경계는 session_room_id (rooms.id)
  source_type = meeting_segment -> 세션 경계는 session_meeting_id (meetings.id)
Room과 Meeting은 서로 다른 테이블이라 room_id 하나로 통칭하지 않는다.
"""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, uuid_pk


class RelatedHistoryMatch(Base):
    __tablename__ = "related_history_matches"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)

    source_type = Column(String(30), nullable=False)  # meeting_segment | room_message
    meeting_segment_id = Column(UUID(as_uuid=True), ForeignKey("meeting_segments.id"), nullable=True)
    room_message_id = Column(UUID(as_uuid=True), ForeignKey("room_messages.id"), nullable=True)

    # 세션 스코프 - source_type에 따라 둘 중 하나만 채워짐
    session_meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id"), nullable=True)
    session_room_id = Column(UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=True)

    match_type = Column(String(30), nullable=False)  # decision_reminder | document_recommendation

    reference_decision_id = Column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=True)
    reference_file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=True)

    confidence_score = Column(Numeric(5, 4), nullable=True)
    matched_at = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('meeting_segment','room_message')",
            name="chk_related_history_source_type",
        ),
        CheckConstraint(
            "match_type IN ('decision_reminder','document_recommendation')",
            name="chk_related_history_match_type",
        ),
        CheckConstraint(
            "(source_type = 'meeting_segment' AND session_meeting_id IS NOT NULL AND session_room_id IS NULL) OR "
            "(source_type = 'room_message' AND session_room_id IS NOT NULL AND session_meeting_id IS NULL)",
            name="chk_related_history_session_exclusive",
        ),
        CheckConstraint(
            "(match_type = 'decision_reminder' AND reference_decision_id IS NOT NULL) OR "
            "(match_type = 'document_recommendation' AND reference_file_id IS NOT NULL)",
            name="chk_related_history_reference_exclusive",
        ),
        # "이 세션에서 이 참조 대상에 이미 알림 줬는지" 조회용
        Index(
            "idx_related_history_session_decision",
            "session_meeting_id", "session_room_id", "reference_decision_id",
        ),
        Index(
            "idx_related_history_session_file",
            "session_meeting_id", "session_room_id", "reference_file_id",
        ),
        # "반복 논의 카운트" 조회용 - 카테고리+결정 기준으로 세션 수를 셈
        Index(
            "idx_related_history_repeat_count",
            "category_id", "reference_decision_id",
        ),
    )