from backend.schemas.agent_schema import AgentState


def _items_from_risk_clauses(risk_clauses: list[dict]) -> list[dict]:
    items = []
    for clause in risk_clauses:
        if not isinstance(clause, dict):
            continue

        clause_label = clause.get("clause") or clause.get("source_clause") or ""

        items.append({
            "task": f"{clause_label} 조항을 의뢰인에게 설명".strip(),
            "reason": clause.get("reason") or clause.get("issue") or "",
            "priority": clause.get("risk_level") or "medium",
            "status": "todo",
            "source_document_id": clause.get("source_document_id"),
            "source_clause": clause_label,
            "related_legal_refs": clause.get("related_legal_refs") or [],
        })
    return items


def _items_from_missing_checks(missing_checks: list[str]) -> list[dict]:
    return [
        {
            "task": f"{check} 확인",
            "reason": "누락된 확인 항목",
            "priority": "medium",
            "status": "todo",
            "source_document_id": None,
            "source_clause": None,
            "related_legal_refs": [],
        }
        for check in missing_checks
        if check
    ]


def _items_from_recommendations(recommendations: list[str]) -> list[dict]:
    return [
        {
            "task": recommendation,
            "reason": "권고 사항",
            "priority": "medium",
            "status": "todo",
            "source_document_id": None,
            "source_clause": None,
            "related_legal_refs": [],
        }
        for recommendation in recommendations
        if recommendation
    ]


def task_generate_node(state: AgentState) -> dict:
    try:
        risk_clauses = state.get("risk_clauses") or []
        missing_checks = state.get("missing_checks") or []
        recommendations = state.get("recommendations") or []

        action_items = (
            _items_from_risk_clauses(risk_clauses)
            + _items_from_missing_checks(missing_checks)
            + _items_from_recommendations(recommendations)
        )

        return {
            "action_items": action_items,
            "tasks": action_items,
            "current_step": "task_generate_node",
            "error": None,
        }

    except Exception as e:
        return {
            "action_items": state.get("action_items") or [],
            "tasks": state.get("tasks") or [],
            "current_step": "task_generate_node",
            "error": str(e),
        }
