# backend/graphs/states/ai_chat_state.py

# 채팅방 안 개인 AI Chat 질문 처리 상태.
# 검색 범위는 workspace_id와 category_id로 제한한다.

from typing import Any, NotRequired, Required

from backend.graphs.states.common_state import CommonState


class AIChatState(CommonState, total=False):
    # 세션 및 질문
    session_id: Required[str]
    room_id: Required[str]
    user_id: Required[str]
    user_message: Required[str]
    chat_history: NotRequired[list[dict[str, Any]]]

    # 검색
    rag_query: NotRequired[str]
    query_embedding: NotRequired[list[float]]
    chunk_search_results: NotRequired[list[dict[str, Any]]]
    code_fact_search_results: NotRequired[list[dict[str, Any]]]

    # 답변 생성
    answer: NotRequired[str]
    answer_model_name: NotRequired[str]

    # 저장 결과
    user_message_id: NotRequired[str]
    assistant_message_id: NotRequired[str]
    retrieved_sources: NotRequired[list[dict[str, Any]]]
    saved_source_ids: NotRequired[list[str]]