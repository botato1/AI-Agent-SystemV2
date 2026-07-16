# backend/graphs/contradiction_graph.py

# ContradictionState 그래프 조립.
# 지금은 노드가 하나뿐이라 단순 통과 구조지만, 후보 필터/근거 검색/LLM 판단을
# 별도 노드로 쪼갤 때를 대비해 그래프 형태로 조립해둔다.

from langgraph.graph import END, START, StateGraph

from backend.graphs.nodes.contradiction_detect import contradiction_detect_node
from backend.graphs.states.contradiction_state import ContradictionState


def build_contradiction_graph():
    graph = StateGraph(ContradictionState)

    graph.add_node("contradiction_detect_node", contradiction_detect_node)

    graph.add_edge(START, "contradiction_detect_node")
    graph.add_edge("contradiction_detect_node", END)

    return graph.compile()


contradiction_graph = build_contradiction_graph()


def run_contradiction_detection(
    *,
    workspace_id: str,
    category_id: str,
    source_type: str,
    statement_text: str,
    meeting_segment_id: str | None = None,
    room_message_id: str | None = None,
) -> ContradictionState:
    """
    회의 세그먼트/채팅 메시지 하나에 대해 모순 감지 그래프를 실행한다.

    source_type='meeting_segment'이면 meeting_segment_id를,
    source_type='room_message'이면 room_message_id를 채워서 호출할 것.
    """
    initial_state: ContradictionState = {
        "workspace_id": workspace_id,
        "category_id": category_id,
        "source_type": source_type,
        "statement_text": statement_text,
    }
    if meeting_segment_id:
        initial_state["meeting_segment_id"] = meeting_segment_id
    if room_message_id:
        initial_state["room_message_id"] = room_message_id

    return contradiction_graph.invoke(initial_state)
