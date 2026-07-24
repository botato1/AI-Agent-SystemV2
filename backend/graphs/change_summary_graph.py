# backend/graphs/change_summary_graph.py

from langgraph.graph import END, START, StateGraph

from backend.graphs.nodes.change_summary_generate import change_summary_generate_node
from backend.graphs.states.contradiction_resolution_state import ContradictionResolutionState


def build_change_summary_graph():
    graph = StateGraph(ContradictionResolutionState)
    graph.add_node("change_summary_generate", change_summary_generate_node)
    graph.add_edge(START, "change_summary_generate")
    graph.add_edge("change_summary_generate", END)
    return graph.compile()


change_summary_graph = build_change_summary_graph()


def run_change_summary_generation(
    *, contradiction_id: str, workspace_id: str, category_id: str
) -> dict:
    initial_state: ContradictionResolutionState = {
        "workspace_id": workspace_id,
        "category_id": category_id,
        "contradiction_id": contradiction_id,
    }
    return change_summary_graph.invoke(initial_state)
