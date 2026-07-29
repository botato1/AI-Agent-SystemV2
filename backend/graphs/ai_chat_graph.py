# backend/graphs/ai_chat_graph.py

from langgraph.graph import END, START, StateGraph

from backend.graphs.nodes.ai_chat_answer import ai_chat_answer_node
from backend.graphs.states.ai_chat_state import AIChatState


def build_ai_chat_graph():
    graph = StateGraph(AIChatState)
    graph.add_node("ai_chat_answer", ai_chat_answer_node)
    graph.add_edge(START, "ai_chat_answer")
    graph.add_edge("ai_chat_answer", END)
    return graph.compile()


ai_chat_graph = build_ai_chat_graph()


def run_ai_chat_answer(
    *,
    session_id: str,
    workspace_id: str,
    category_id: str,
    user_id: str,
    user_message: str,
    room_id: str | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    initial_state: AIChatState = {
        "workspace_id": workspace_id,
        "category_id": category_id,
        "session_id": session_id,
        "user_id": user_id,
        "user_message": user_message,
    }
    if room_id is not None:
        initial_state["room_id"] = room_id
    if chat_history is not None:
        initial_state["chat_history"] = chat_history
    return ai_chat_graph.invoke(initial_state)