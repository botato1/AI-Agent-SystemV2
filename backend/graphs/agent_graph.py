from langgraph.graph import StateGraph, START, END

from backend.schemas.agent_schema import AgentState
from backend.graphs.nodes.classifier import classifier_node
from backend.graphs.nodes.document_context import document_context_node
from backend.graphs.nodes.clause_extractor import clause_extractor_node
from backend.graphs.nodes.fact_extractor import fact_extractor_node
from backend.graphs.nodes.answer import answer_node


# TODO: law_retrieval_node, case_law_retrieval_node, legal_analysis_node,
# task_generate_node, case_card_node가 구현되면 clause_extractor_node /
# fact_extractor_node 뒤에 이어붙이고, 지금 answer_node로 바로 보내는
# 임시 엣지를 제거할 것.

def route_after_classify(state: AgentState) -> str:
    if (
        state.get("need_rag")
        or state.get("need_legal_analysis")
        or state.get("need_task_generate")
        or state.get("need_case_card")
    ):
        return "document_context_node"
    return "answer_node"


def route_after_document_context(state: AgentState) -> str:
    document_type = state.get("document_type")
    if document_type == "contract":
        return "clause_extractor_node"
    if document_type in ("consultation_audio", "consultation_note", "voice"):
        return "fact_extractor_node"
    return "answer_node"


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("classifier_node", classifier_node)
    graph.add_node("document_context_node", document_context_node)
    graph.add_node("clause_extractor_node", clause_extractor_node)
    graph.add_node("fact_extractor_node", fact_extractor_node)
    graph.add_node("answer_node", answer_node)

    graph.add_edge(START, "classifier_node")

    graph.add_conditional_edges(
        "classifier_node",
        route_after_classify,
        {
            "document_context_node": "document_context_node",
            "answer_node": "answer_node",
        },
    )

    graph.add_conditional_edges(
        "document_context_node",
        route_after_document_context,
        {
            "clause_extractor_node": "clause_extractor_node",
            "fact_extractor_node": "fact_extractor_node",
            "answer_node": "answer_node",
        },
    )

    graph.add_edge("clause_extractor_node", "answer_node")
    graph.add_edge("fact_extractor_node", "answer_node")
    graph.add_edge("answer_node", END)

    return graph.compile()


agent_graph = build_agent_graph()
