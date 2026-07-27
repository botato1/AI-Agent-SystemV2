# backend/services/judgment_service.py

"""실시간 판단 파이프라인(결정 리마인더/문서 추천/반복논의) 통합 실행.

decision_judgment -> document_judgment -> priority 순서로 판단하고,
팝업이 나오면 Notification으로 저장한다. contradiction 타입은 이미
contradictions 테이블 + 기존 조회 경로로 노출되므로 여기서는 스킵한다.
"""

import uuid

from backend.db.crud import notification_crud
from backend.db.session import SessionLocal
from backend.modules.judgment import decision_judgment, document_judgment, priority

_SKIP_NOTIFICATION_POPUP_TYPES = {"contradiction"}

_POPUP_TITLE = {
    "decision_reminder": "이전 결정 리마인더",
    "repeat_discussion": "반복 논의 알림",
    "document_recommendation": "관련 문서 추천",
}


def run_judgment_pipeline(
    *,
    workspace_id: str,
    category_id: str,
    source_type: str,  # "meeting_segment" | "room_message"
    statement_text: str,
    notify_user_id: str,
    meeting_segment_id: str | None = None,
    room_message_id: str | None = None,
    session_meeting_id: str | None = None,
    session_room_id: str | None = None,
) -> None:
    """발화/메시지 하나마다 백그라운드로 호출한다. 자체 DB 세션을 새로 연다."""
    db = SessionLocal()
    try:
        source_id = uuid.UUID(meeting_segment_id) if meeting_segment_id else uuid.UUID(room_message_id)
        session_kwargs = {
            "session_meeting_id": uuid.UUID(session_meeting_id) if session_meeting_id else None,
            "session_room_id": uuid.UUID(session_room_id) if session_room_id else None,
        }

        decision_result = decision_judgment.judge(
            db,
            workspace_id=uuid.UUID(workspace_id),
            category_id=uuid.UUID(category_id),
            source_type=source_type,
            source_id=source_id,
            statement=statement_text,
            **session_kwargs,
        )

        document_result = None
        if decision_result.get("case") == "none":
            document_result = document_judgment.judge(
                db,
                workspace_id=uuid.UUID(workspace_id),
                category_id=uuid.UUID(category_id),
                source_type=source_type,
                source_id=source_id,
                statement=statement_text,
                **session_kwargs,
            )

        popup = priority.select_popup(decision_result, document_result)
        if not popup or popup["type"] in _SKIP_NOTIFICATION_POPUP_TYPES:
            return

        notification_crud.create_notification(
            db,
            user_id=uuid.UUID(notify_user_id),
            workspace_id=uuid.UUID(workspace_id),
            type=popup["type"],
            title=_POPUP_TITLE.get(popup["type"], "알림"),
            message=popup["message"],
            ref_type=source_type,
            ref_id=source_id,
        )

    except Exception as e:
        print(f"[judgment_service] 판단 파이프라인 실패: {repr(e)}")
    finally:
        db.close()