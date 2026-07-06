from langgraph.graph import StateGraph, START, END

from backend.schemas.agent_schema import AgentState
from backend.graphs.nodes.classifier import classifier_node
from backend.graphs.nodes.document_context import document_context_node
from backend.graphs.nodes.clause_extractor import clause_extractor_node
from backend.graphs.nodes.fact_extractor import fact_extractor_node
from backend.graphs.nodes.law_retrieval import law_retrieval_node
from backend.graphs.nodes.case_law_retrieval import case_law_retrieval_node
from backend.graphs.nodes.legal_analysis import legal_analysis_node
from backend.graphs.nodes.task_generate import task_generate_node
from backend.graphs.nodes.case_card import case_card_node
from backend.graphs.nodes.answer import answer_node


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
    return "law_retrieval_node"


def route_after_case_law_retrieval(state: AgentState) -> str:
    if (
        state.get("need_legal_analysis")
        or state.get("need_task_generate")
        or state.get("need_case_card")
    ):
        return "legal_analysis_node"
    return "answer_node"


def route_after_legal_analysis(state: AgentState) -> str:
    if state.get("need_task_generate"):
        return "task_generate_node"
    if state.get("need_case_card"):
        return "case_card_node"
    return "answer_node"


def route_after_task_generate(state: AgentState) -> str:
    if state.get("need_case_card"):
        return "case_card_node"
    return "answer_node"


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("classifier_node", classifier_node)
    graph.add_node("document_context_node", document_context_node)
    graph.add_node("clause_extractor_node", clause_extractor_node)
    graph.add_node("fact_extractor_node", fact_extractor_node)
    graph.add_node("law_retrieval_node", law_retrieval_node)
    graph.add_node("case_law_retrieval_node", case_law_retrieval_node)
    graph.add_node("legal_analysis_node", legal_analysis_node)
    graph.add_node("task_generate_node", task_generate_node)
    graph.add_node("case_card_node", case_card_node)
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
            "law_retrieval_node": "law_retrieval_node",
        },
    )

    graph.add_edge("clause_extractor_node", "law_retrieval_node")
    graph.add_edge("fact_extractor_node", "law_retrieval_node")
    graph.add_edge("law_retrieval_node", "case_law_retrieval_node")

    graph.add_conditional_edges(
        "case_law_retrieval_node",
        route_after_case_law_retrieval,
        {
            "legal_analysis_node": "legal_analysis_node",
            "answer_node": "answer_node",
        },
    )

    graph.add_conditional_edges(
        "legal_analysis_node",
        route_after_legal_analysis,
        {
            "task_generate_node": "task_generate_node",
            "case_card_node": "case_card_node",
            "answer_node": "answer_node",
        },
    )

    graph.add_conditional_edges(
        "task_generate_node",
        route_after_task_generate,
        {
            "case_card_node": "case_card_node",
            "answer_node": "answer_node",
        },
    )

    graph.add_edge("case_card_node", "answer_node")
    graph.add_edge("answer_node", END)

    return graph.compile()


agent_graph = build_agent_graph()
