import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.schemas.agent_schema import AgentState
from backend.schemas.case_card_schema import CaseCardSchema


# TODO: case_cards 테이블/CRUD가 아직 없음. 지금은 case_card 딕셔너리를
# 만들어서 state에만 반영하고, DB UPSERT는 하지 않는다.
# db/database.py에 case_cards 테이블 추가 + db/crud.py에
# upsert_case_card(case_card: dict) 구현되면 아래에서 호출해서 영속화할 것.


def case_card_node(state: AgentState) -> dict:
    conversation_id = state.get("conversation_id") or state.get("room_id") or ""

    try:
        now = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
        summary = state.get("case_summary") or state.get("summary")

        related_legal_refs = state.get("legal_refs") or []
        action_items = state.get("action_items") or []

        risk_clauses = state.get("risk_clauses") or []
        priority = "high" if any(
            isinstance(clause, dict) and clause.get("risk_level") == "high"
            for clause in risk_clauses
        ) else "medium"

        existing_case_card = state.get("case_card") or {}

        case_card = CaseCardSchema(
            id=existing_case_card.get("id") or str(uuid.uuid4()),
            room_id=state.get("room_id"),
            conversation_id=conversation_id,
            summary=summary,
            related_document_ids=state.get("document_ids") or [],
            related_legal_refs=related_legal_refs,
            action_items=action_items,
            priority=existing_case_card.get("priority") or priority,
            status=existing_case_card.get("status") or "open",
            created_at=existing_case_card.get("created_at") or now,
            updated_at=now,
        )

        return {
            "case_card": case_card.model_dump(),
            "current_step": "case_card_node",
            "error": None,
        }

    except Exception as e:
        return {
            "case_card": state.get("case_card"),
            "current_step": "case_card_node",
            "error": str(e),
        }
