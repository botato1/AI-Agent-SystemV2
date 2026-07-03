from backend.schemas.agent_schema import AgentState
from backend.schemas.type_schema import QuestionTypeV2, DEFAULT_QUESTION_TYPE


# TODO: 승주의 ollama_service.classify_for_graph()가 V1 question_type만
# 반환하는 상태라 아직 사용하지 않음. V2 법률 의도 분류로 마이그레이션되면
# 이 노드를 LLM 기반으로 교체할 것.

CONTRACT_KEYWORDS = ["계약서", "계약", "조항", "위험", "리스크", "검토"]
STATUTE_KEYWORDS = ["법조문", "법령", "조문", "법률 근거"]
PRECEDENT_KEYWORDS = ["판례", "판결"]
LEGAL_SEARCH_KEYWORDS = ["법", "근거", "찾아줘"]


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _resolve_question_type(user_message: str) -> QuestionTypeV2:
    if _contains_any(user_message, CONTRACT_KEYWORDS):
        return "contract_risk_check"

    if _contains_any(user_message, PRECEDENT_KEYWORDS):
        return "precedent_search"

    if _contains_any(user_message, STATUTE_KEYWORDS):
        return "statute_search"

    if _contains_any(user_message, LEGAL_SEARCH_KEYWORDS):
        return "legal_search"

    return "general_answer"


def _build_need_flags(question_type: QuestionTypeV2) -> dict:
    return {
        "need_general_answer": question_type == "general_answer",
        "need_memory": False,
        "need_rag": question_type in {
            "contract_risk_check",
            "statute_search",
            "precedent_search",
            "legal_search",
        },
        "need_task_extract": False,
        "need_legal_analysis": question_type in {
            "contract_risk_check",
            "consultation_summary",
        },
        "need_task_generate": False,
        "need_case_card": question_type == "consultation_summary",
        "need_user_documents": question_type in {
            "contract_risk_check",
            "consultation_summary",
        },
        "need_legal_corpus": question_type in {
            "statute_search",
            "precedent_search",
            "legal_search",
        },
    }


def classifier_node(state: AgentState) -> dict:
    user_message = state.get("user_message", "")

    try:
        question_type = _resolve_question_type(user_message)
        need_flags = _build_need_flags(question_type)

        return {
            "question_type": question_type,
            **need_flags,
            "current_step": "classify_node",
            "error": None,
        }

    except Exception as e:
        return {
            "question_type": DEFAULT_QUESTION_TYPE,
            "need_general_answer": True,
            "need_memory": False,
            "need_rag": False,
            "need_task_extract": False,
            "need_legal_analysis": False,
            "need_task_generate": False,
            "need_case_card": False,
            "need_user_documents": False,
            "need_legal_corpus": False,
            "current_step": "classify_node",
            "error": str(e),
        }
