from backend.schemas.agent_schema import AgentState
from backend.services.rag_service import rag_service


def _build_rag_query(state: AgentState) -> str:
    user_message = state.get("user_message", "")

    contract_clauses = state.get("contract_clauses") or []
    if contract_clauses:
        clause_text = " ".join(
            clause.get("content", "") for clause in contract_clauses if isinstance(clause, dict)
        )
        return f"{user_message}\n{clause_text}".strip()

    case_summary = state.get("case_summary")
    if case_summary:
        return f"{user_message}\n{case_summary}".strip()

    return user_message


def law_retrieval_node(state: AgentState) -> dict:
    try:
        rag_query = _build_rag_query(state)

        result = rag_service.retrieve_relevant_knowledge_sync(
            query=rag_query,
            filter=state.get("rag_filter"),
            question_type=state.get("question_type", "general_answer"),
            room_id=state.get("conversation_id") or state.get("room_id") or "",
        )

        documents = result.get("data") or []

        law_refs = [
            {
                "ref_type": "law",
                "title": doc.get("title"),
                "source": doc.get("source"),
                "document_id": doc.get("document_id"),
                "score": doc.get("score"),
            }
            for doc in documents
        ]

        law_context = [
            {
                "content": doc.get("content"),
                "title": doc.get("title"),
                "source": doc.get("source"),
                "score": doc.get("score"),
            }
            for doc in documents
        ]

        return {
            "rag_query": rag_query,
            "rag_context": (state.get("rag_context") or []) + law_context,
            "legal_refs": (state.get("legal_refs") or []) + law_refs,
            "sources": (state.get("sources") or []) + law_refs,
            "rag_search_result": result,
            "retrieved_docs": documents,
            "low_confidence": bool(state.get("low_confidence")) or bool(result.get("low_confidence")),
            "current_step": "law_retrieval_node",
            "error": None,
        }

    except Exception as e:
        return {
            "rag_query": state.get("rag_query"),
            "rag_context": state.get("rag_context") or [],
            "legal_refs": state.get("legal_refs") or [],
            "sources": state.get("sources") or [],
            "rag_search_result": None,
            "retrieved_docs": [],
            "low_confidence": True,
            "current_step": "law_retrieval_node",
            "error": str(e),
        }
