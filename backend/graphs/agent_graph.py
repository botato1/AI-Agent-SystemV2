# backend/graphs/agent_graph.py

from langgraph.graph import END, START, StateGraph

from backend.schemas.agent_schema import AgentState
from backend.graphs.nodes.classifier import classifier_node
from backend.graphs.nodes.document_context import document_context_node
from backend.graphs.nodes.clause_extractor import clause_extractor_node
from backend.graphs.nodes.fact_extractor import fact_extractor_node
from backend.graphs.nodes.law_retrieval import law_retrieval_node
from backend.graphs.nodes.case_law_retrieval import case_law_retrieval_node
from backend.graphs.nodes.legal_analysis import legal_analysis_node
from backend.graphs.nodes.task_generate import task_generate_node
from backend.graphs.nodes.answer import answer_node


def route_after_classify(state: AgentState) -> str:
    """
    분류 결과에 따라 문서 컨텍스트를 조회하거나
    바로 일반 답변을 생성한다.
    """
    if (
        state.get("need_rag")
        or state.get("need_legal_analysis")
        or state.get("need_task_generate")
    ):
        return "document_context_node"

    return "answer_node"


def route_after_document_context(state: AgentState) -> str:
    """
    연결된 문서 유형에 따라 전처리 노드를 선택한다.
    """
    document_type = state.get("document_type")

    if document_type == "contract":
        return "clause_extractor_node"

    if document_type in (
        "consultation_audio",
        "consultation_note",
        "voice",
    ):
        return "fact_extractor_node"

    return "law_retrieval_node"


def route_after_case_law_retrieval(state: AgentState) -> str:
    """
    법률 분석이나 업무 생성이 필요한 경우 법률 분석 노드로 이동한다.
    그렇지 않으면 바로 답변을 생성한다.
    """
    if (
        state.get("need_legal_analysis")
        or state.get("need_task_generate")
    ):
        return "legal_analysis_node"

    return "answer_node"


def route_after_legal_analysis(state: AgentState) -> str:
    """
    후속 업무 생성이 필요한 경우 업무 생성 노드로 이동한다.
    """
    if state.get("need_task_generate"):
        return "task_generate_node"

    return "answer_node"


def build_agent_graph():
    graph = StateGraph(AgentState)

    # 노드 등록
    graph.add_node("classifier_node", classifier_node)
    graph.add_node("document_context_node", document_context_node)
    graph.add_node("clause_extractor_node", clause_extractor_node)
    graph.add_node("fact_extractor_node", fact_extractor_node)
    graph.add_node("law_retrieval_node", law_retrieval_node)
    graph.add_node(
        "case_law_retrieval_node",
        case_law_retrieval_node,
    )
    graph.add_node("legal_analysis_node", legal_analysis_node)
    graph.add_node("task_generate_node", task_generate_node)
    graph.add_node("answer_node", answer_node)

    # 시작
    graph.add_edge(START, "classifier_node")

    # 질문 분류 후 라우팅
    graph.add_conditional_edges(
        "classifier_node",
        route_after_classify,
        {
            "document_context_node": "document_context_node",
            "answer_node": "answer_node",
        },
    )

    # 문서 유형별 라우팅
    graph.add_conditional_edges(
        "document_context_node",
        route_after_document_context,
        {
            "clause_extractor_node": "clause_extractor_node",
            "fact_extractor_node": "fact_extractor_node",
            "law_retrieval_node": "law_retrieval_node",
        },
    )

    # 문서 전처리 후 법령 검색
    graph.add_edge(
        "clause_extractor_node",
        "law_retrieval_node",
    )
    graph.add_edge(
        "fact_extractor_node",
        "law_retrieval_node",
    )

    # 법령 검색 후 판례 검색
    graph.add_edge(
        "law_retrieval_node",
        "case_law_retrieval_node",
    )

    # 판례 검색 후 법률 분석 또는 답변
    graph.add_conditional_edges(
        "case_law_retrieval_node",
        route_after_case_law_retrieval,
        {
            "legal_analysis_node": "legal_analysis_node",
            "answer_node": "answer_node",
        },
    )

    # 법률 분석 후 업무 생성 또는 답변
    graph.add_conditional_edges(
        "legal_analysis_node",
        route_after_legal_analysis,
        {
            "task_generate_node": "task_generate_node",
            "answer_node": "answer_node",
        },
    )

    # 업무 생성 후 답변
    graph.add_edge(
        "task_generate_node",
        "answer_node",
    )

    # 종료
    graph.add_edge("answer_node", END)

    return graph.compile()


agent_graph = build_agent_graph()