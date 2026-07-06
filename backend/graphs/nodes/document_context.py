from backend.schemas.agent_schema import AgentState
from backend.db.crud import (
    get_document_by_id,
    get_document_ids_by_room,
    get_document_by_title_and_room,
)


def _resolve_document_ids(state: AgentState, room_id: str, user_id: str) -> list[str]:
    if state.get("target_document_id"):
        return [state["target_document_id"]]

    if state.get("target_document_ids"):
        return list(state["target_document_ids"])

    target_filename = state.get("target_filename")
    if target_filename and room_id:
        document = get_document_by_title_and_room(room_id, target_filename, user_id)
        if document:
            return [document["id"]]

    if room_id:
        return get_document_ids_by_room(room_id, user_id)

    return []


def document_context_node(state: AgentState) -> dict:
    room_id = state.get("conversation_id") or state.get("room_id") or ""
    user_id = state.get("user_id")

    try:
        document_ids = _resolve_document_ids(state, room_id, user_id)

        document_context = []
        for document_id in document_ids:
            document = get_document_by_id(document_id)
            if not document:
                continue

            document_context.append({
                "document_id": document.get("id"),
                "document_type": document.get("type"),
                "source": document.get("source"),
                "filename": document.get("title"),
                "page_count": document.get("page_count"),
            })

        document_type = document_context[0]["document_type"] if document_context else None

        rag_filter = {**(state.get("rag_filter") or {}), "conversation_id": room_id}
        if document_ids:
            rag_filter["document_id"] = {"$in": document_ids}

        return {
            "document_ids": document_ids,
            "document_context": document_context,
            "document_type": document_type,
            "rag_filter": rag_filter,
            "current_step": "document_context_node",
            "error": None,
        }

    except Exception as e:
        return {
            "document_ids": [],
            "document_context": [],
            "document_type": None,
            "rag_filter": state.get("rag_filter") or {},
            "current_step": "document_context_node",
            "error": str(e),
        }