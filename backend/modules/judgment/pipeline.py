"""실시간 판단 파이프라인 진입점

발화 하나를 받아 1-1(decision_judgment) → 1-2(document_judgment, 1-1이 "none"일 때만)
→ 1-4(priority) 순으로 실행해서 최종 출력 하나를 고른다.

세션 시작 시 1회만 도는 1-3(agenda_reminder)은 발화 단위 트리거가 아니라
회의/방 시작 단위라 여기 포함되지 않는다 - 별도로 호출해야 한다.
"""

import uuid

from sqlalchemy.orm import Session

from backend.modules.judgment import decision_judgment, document_judgment, priority


def judge_statement(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    source_type: str,  # 'meeting_segment' | 'room_message'
    source_id: uuid.UUID,
    statement: str,
    session_meeting_id: uuid.UUID | None = None,
    session_room_id: uuid.UUID | None = None,
) -> dict | None:
    """발화 하나를 판단해서 화면에 표시할 출력 하나를 반환한다. 없으면 None."""
    session_kwargs = {"session_meeting_id": session_meeting_id, "session_room_id": session_room_id}

    decision_result = decision_judgment.judge(
        db,
        workspace_id=workspace_id, category_id=category_id,
        source_type=source_type, source_id=source_id, statement=statement,
        **session_kwargs,
    )

    document_result = None
    if decision_result["case"] == "none":
        document_result = document_judgment.judge(
            db,
            workspace_id=workspace_id, category_id=category_id,
            source_type=source_type, source_id=source_id, statement=statement,
            **session_kwargs,
        )

    return priority.select_popup(decision_result, document_result)
