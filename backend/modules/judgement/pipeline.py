"""실시간 판단 파이프라인 — 전체 진입점

새 meeting_segment 또는 room_message가 생성될 때마다 호출한다.

1-1(decision_judgment) 먼저 실행 → "none"이면 1-2(document_judgment)로 넘김
→ 1-4(priority)로 최종 팝업 하나만 선택 → 반환

1-3(agenda_reminder)은 발화 트리거가 아니라 세션 시작 트리거라 이 함수와
별도로 호출한다 (judgment.agenda_reminder.check_on_session_start 직접 사용).
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
) -> dict:
    """
    발화 하나를 받아 1-1 → (필요시) 1-2 → 1-4 순서로 판단하고,
    사용자에게 보여줄 팝업 최대 1개를 반환한다.

    Returns:
        {"popup": dict|None, "decision_case": str, "document_case": str|None}
    """
    common_kwargs = dict(
        db=db, workspace_id=workspace_id, category_id=category_id,
        source_type=source_type, source_id=source_id, statement=statement,
        session_meeting_id=session_meeting_id, session_room_id=session_room_id,
    )

    decision_result = decision_judgment.judge(**common_kwargs)

    document_result = None
    if decision_result["case"] == "none":
        # DECISION_COLLECTION에 매칭이 없었을 때만 1-2로 넘김
        document_result = document_judgment.judge(**common_kwargs)

    popup = priority.select_popup(decision_result, document_result)

    return {
        "popup": popup,
        "decision_case": decision_result["case"],
        "document_case": document_result["case"] if document_result else None,
    }