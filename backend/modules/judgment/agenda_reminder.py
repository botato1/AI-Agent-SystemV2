"""실시간 판단 파이프라인 1-3: 미해결 안건 리마인더

지난 회의에서 못 끝낸 할 일이 있으면 새 세션 시작 시 알려준다.
발화마다 도는 게 아니라 세션(방/회의) 시작 시점 1회성 트리거 - 순수 쿼리,
LLM/벡터검색 불필요.
"""

import uuid

from sqlalchemy.orm import Session

from backend.db.crud import meeting_crud


def check_on_session_start(db: Session, category_id: uuid.UUID) -> dict:
    """
    새 방/회의가 시작될 때 호출한다.

    Returns:
        {"popup": {"type": "agenda_reminder", "message": str, "items": list[dict]}}
        미해결 항목이 없어도 팝업은 항상 반환한다 ("없습니다" 표시, 설계 문서 1-3 참조).
    """
    items = meeting_crud.list_open_action_items_by_category(db, category_id)

    if not items:
        return {
            "popup": {
                "type": "agenda_reminder",
                "message": "미해결된 안건이 없습니다",
                "items": [],
            }
        }

    item_summaries = [
        {
            "id": str(item.id),
            "title": item.title,
            "assignee": item.assignee_label,
            "due_at": item.due_at.isoformat() if item.due_at else None,
        }
        for item in items
    ]

    assignee_list = ", ".join(
        f"{item.title}({item.assignee_label or '담당자 미정'})" for item in items
    )

    return {
        "popup": {
            "type": "agenda_reminder",
            "message": f"미해결 할 일이 {len(items)}건 있습니다: {assignee_list}",
            "items": item_summaries,
        }
    }