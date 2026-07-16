# backend/graphs/meeting_postprocess_graph.py

# MeetingPostprocessState 그래프 조립.
# 지금은 노드 하나(meeting_postprocess_node)뿐인 단순 통과 구조.

from langgraph.graph import END, START, StateGraph

from backend.graphs.nodes.meeting_postprocess import meeting_postprocess_node
from backend.graphs.states.meeting_postprocess_state import MeetingPostprocessState


def build_meeting_postprocess_graph():
    graph = StateGraph(MeetingPostprocessState)

    graph.add_node("meeting_postprocess_node", meeting_postprocess_node)

    graph.add_edge(START, "meeting_postprocess_node")
    graph.add_edge("meeting_postprocess_node", END)

    return graph.compile()


meeting_postprocess_graph = build_meeting_postprocess_graph()


def run_meeting_postprocess(*, meeting_id: str, workspace_id: str, category_id: str) -> MeetingPostprocessState:
    """회의 종료 후(status='processing') 호출한다."""
    initial_state: MeetingPostprocessState = {
        "workspace_id": workspace_id,
        "category_id": category_id,
        "meeting_id": meeting_id,
        "source_file_id": "",
    }
    return meeting_postprocess_graph.invoke(initial_state)
