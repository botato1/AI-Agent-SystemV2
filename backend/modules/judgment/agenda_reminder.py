"""실시간 판단 파이프라인 1-3: 미해결 안건 리마인더

decisions 테이블에 status='pending'으로 남아있는 미해결 안건(재논의했지만
결론이 안 난 것, decision_transition.py Case B 참조)이 있으면 새 세션 시작 시
알려준다. 할 일(tasks)은 대시보드 탭에서 별도 관리되는 무관한 개념이라 여기서
다루지 않는다 (설계 변경 - 기존엔 tasks를 조회했으나 분리).

발화마다 도는 게 아니라 세션(방/회의) 시작 시점 1회성 트리거 - 순수 쿼리,
LLM/벡터검색 불필요.
"""

import uuid

from sqlalchemy.orm import Session

from backend.db.modules import Decision, Meeting


def check_on_session_start(db: Session, category_id: uuid.UUID) -> dict:
    """
    새 방/회의가 시작될 때 호출한다.

    Returns:
        {"popup": {"type": "agenda_reminder", "message": str, "items": list[dict]}}
        미해결 항목이 없어도 항상 반환한다 ("없습니다" 표시, 설계 문서 1-3 참조).
    """
    # Decision에 category_id가 없어서 Meeting을 조인해서 필터링한다.
    items = (
        db.query(Decision)
        .join(Meeting, Decision.meeting_id == Meeting.id)
        .filter(
            Meeting.category_id == category_id,
            Decision.status == "pending",
            Decision.deleted_at.is_(None),
        )
        .order_by(Decision.decided_at.desc())
        .all()
    )

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
            "decision_text": item.decision_text,
            "reason": item.reason,
        }
        for item in items
    ]

    title_list = ", ".join(item.title for item in items)

    return {
        "popup": {
            "type": "agenda_reminder",
            "message": f"미해결 안건이 {len(items)}건 있습니다: {title_list}",
            "items": item_summaries,
        }
    }
