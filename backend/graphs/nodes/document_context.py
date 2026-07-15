from backend.schemas.agent_schema import AgentState

# TODO: 아래 함수들은 legacy 문서 조회 crud로, 새 도메인(workspace_files)으로
# 마이그레이션되지 않았다. 노드 로직 재설계 시 file_crud 기반으로 교체 필요.
# 지금은 import 에러만 막아두는 임시 스텁이며 호출 시 의도적으로 실패한다.

def _not_implemented(name: str):
    raise NotImplementedError(f"{name}은 아직 새 도메인으로 마이그레이션되지 않았습니다.")


def get_document_by_id(*args, **kwargs):
    _not_implemented("get_document_by_id")


def get_document_ids_by_room(*args, **kwargs):
    _not_implemented("get_document_ids_by_room")


def get_document_by_title_and_room(*args, **kwargs):
    _not_implemented("get_document_by_title_and_room")


# TODO: PR #7(feature/backend)이 merge되어 get_document_by_id_for_user()가
# 들어오면 room_id 대조가 아니라 user_id 기준으로 완전히 검증하도록 교체할 것.
def _verify_document_ids_belong_to_room(document_ids: list[str], room_id: str) -> list[str]:
    verified = []
    for document_id in document_ids:
        document = get_document_by_id(document_id)
        if document and document.get("conversation_id") == room_id:
            verified.append(document_id)
    return verified


def _resolve_document_ids(state: AgentState, room_id: str, user_id: str) -> list[str]:
    if state.get("target_document_id"):
        return _verify_document_ids_belong_to_room([state["target_document_id"]], room_id)

    if state.get("target_document_ids"):
        return _verify_document_ids_belong_to_room(list(state["target_document_ids"]), room_id)

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