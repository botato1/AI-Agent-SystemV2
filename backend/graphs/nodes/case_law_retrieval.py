from backend.schemas.agent_schema import AgentState
from backend.services.rag_service import rag_service
from backend.graphs.nodes.law_retrieval import _build_rag_query


def case_law_retrieval_node(state: AgentState) -> dict:
    try:
        rag_query = _build_rag_query(state)

        result = rag_service.retrieve_relevant_knowledge_sync(
            query=rag_query,
            filter=state.get("rag_filter"),
            question_type=state.get("question_type", "general_answer"),
            room_id=state.get("conversation_id") or state.get("room_id") or "",
        )

        documents = result.get("data") or []

        # 실제 RAG 검색으로 반환된 결과만 여기 들어오므로(LLM이 지어낸 판례가 아님)
        # is_verified=True로 표시한다. LLM 답변이 이 목록에 없는 판례를 인용하면
        # 그건 검증 안 된 것이므로 legal_analysis_node/answer_node에서 걸러야 한다.
        precedent_refs = [
            {
                "ref_type": "precedent",
                "title": doc.get("title"),
                "source": doc.get("source"),
                "document_id": doc.get("document_id"),
                "score": doc.get("score"),
                "is_verified": True,
            }
            for doc in documents
        ]

        # AgentState.rag_context는 v1 호환을 위해 문자열로 다룬다
        # (answer_node/ollama_service가 rag_context.strip()을 호출함).
        precedent_context_text = "\n\n".join(
            f"[{doc.get('title', '')}]\n{doc.get('content', '')}" for doc in documents
        )
        existing_rag_context = state.get("rag_context") or ""
        merged_rag_context = (
            f"{existing_rag_context}\n\n{precedent_context_text}".strip()
            if existing_rag_context
            else precedent_context_text
        )

        verified_sources = [ref for ref in precedent_refs if ref["is_verified"]]

        return {
            "rag_context": merged_rag_context,
            "legal_refs": (state.get("legal_refs") or []) + precedent_refs,
            "sources": (state.get("sources") or []) + verified_sources,
            "low_confidence": bool(state.get("low_confidence")) or bool(result.get("low_confidence")),
            "current_step": "case_law_retrieval_node",
            "error": None,
        }

    except Exception as e:
        return {
            "rag_context": state.get("rag_context") or "",
            "legal_refs": state.get("legal_refs") or [],
            "sources": state.get("sources") or [],
            "low_confidence": True,
            "current_step": "case_law_retrieval_node",
            "error": str(e),
        }
