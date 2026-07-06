from backend.schemas.agent_schema import AgentState
from backend.services.ollama_service import ollama_service


# 키워드 상수
VALID_QUESTION_TYPES = {
    "general",
    "rag_search",
    "legal_analysis",
    "legal_task_generate",
    "case_card_generate",
}

LEGAL_ANALYSIS_KEYWORDS = [
    "계약서", "계약", "조항", "검토", "분석", "위험", "리스크",
    "법률", "법적", "쟁점", "위반",
]

CASE_CARD_KEYWORDS = [
  "사건 카드", "사건카드", "사건 등록", "사건 저장", "사건 생성",
]

TASK_KEYWORDS = [
    "할 일", "할일", "업무", "작업", "후속", "조치", "처리",
]

RAG_KEYWORDS = [
   "판례", "법령", "조문", "근거", "검색", "찾아줘", "알려줘",
]


# helper 함수
def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _resolve_question_type(question_type: str, user_message:str,) -> str:
    if question_typenote in VALID_QUESTION_TYPES:
        question_type="general"

    if _contains_any(user_message,CASE_CARD_KEYWORDS):
        return "case_card_generate"
        
    if _contains_any(user_message,TASK_KEYWORDS):
        return "legal_task_generate"
        
    if _contains_any(user_message,LEGAL_ANALYSIS_KEYWORDS):
        return "legal_analysis"

    if _contains_any(user_message,RAG_KEYWORDS):
        return "rag_search"

    return question_type

def _build_need_flags(question_type: str) -> dict:
    return {
        "need_general_answer": question_type == "general",
        "need_memory": False,
        "need_rag": question_type in {
            "rag_search",
            "legal_analysis",
            "legal_task_generate",
        },
        "need_legal_analysis": question_type in {
            "legal_analysis",
            "legal_task_generate",
            "case_card_generate",
        },
        "need_task_generate": question_type == "legal_task_generate",
        "need_case_card": question_type == "case_card_generate",
    }



# classifier_node
def classifier_node(state: AgentState) -> dict:
    user_message = state.get("user_message", "")
  
    try:
        classified = ollama_service.classify_for_graph(user_message)

        question_type = classified.get("question_type", "general")
        question_type = _resolve_question_type(question_type, user_message)
        need_flags = _build_need_flags(question_type)

         return {
            "question_type": question_type,
            **need_flags,
            "current_step": "classify_node",
            "error": None,
        }
       
    except Exception as e:
        return {
            **state,
            "question_type": "general",
            "need_general_answer": True,
            "need_memory": False,
            "need_rag": False,
            "need_legal_analysis": False,
            "need_task_generate": False,
            "need_case_card": False,
            "current_step": "classify_node",
            "error": str(e),
        }