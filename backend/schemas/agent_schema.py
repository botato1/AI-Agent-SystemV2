from typing import Any, Literal, Optional, TypedDict, List

# todo: v1/v2 question_type 통합 필요. 지금은 v1/v2가 혼재되어 있음.
# v1 - 지금 실제로 라우팅에 쓰이는 값 (agent_graph.py / classifier.py / ollama_service.py)
QUESTION_TYPES_V1 = [
    "task_from_rag",
    "task_from_memory",
    "knowledge_search",
    "general_answer",
    "summary_from_rag",
]

# v2 - 노드가 이 값들을 실제로 분기/생성하도록 마이그레이션되기 전까지는 미사용(승주랑 qustion_type 맞춰야함. 추후 수정예정)
QUESTION_TYPES_V2 = [
    "general",
    "rag_search",
    "legal_analysis",
    "legal_task_generate",
    "case_card_generate",
]

class AgentState(TypedDict):
    # 1. 기본 요청 정보
    user_id: Optional[str]
    room_id: str            # v1 호환용 -> v2 기능 안정화 되면 삭제
    conversation_id: str    # 사건방 ID
    user_message: str
    source: str
    created_at: str
    messages: List[dict]    # 이전 대화

    # 2. 문서 / STT  파일 처리 결과
    document_json: Optional[dict]
    target_document_id: Optional[str]
    target_filename: Optional[str]
    target_document_ids: Optional[List[str]]
    document_ids: List[str]
    document_context: List[dict]
    document_type: Optional[str]  # contract/consultation_audio/consultation_note/precedent_ref/evidence

    # 계약서 조항 분리 결과
    contract_clauses: List[dict]

    # 3. 이전 대화 / RAG 검색 결과
    memory_context: Optional[str]
    save_target_content: Optional[str]

    # v1 호환: rag_node/task_node/ollama_service는 지금 rag_context를 문자열로 다룸.
    # v2 목표 타입은 list[dict]지만, 노드 로직을 함께 마이그레이션하기 전까지는
    # 실제 런타임 값(str)과 다른 타입 힌트를 선언하지 않는다.
    rag_context: Optional[str]

    # rag_service.retrieve_relevant_knowledge() 반환값 전체
    rag_search_result: Optional[dict]

    rag_query: Optional[str]
    rag_filter: Optional[dict]
    retrieved_docs: List[dict]
    low_confidence: bool
    sources: List[dict]
    legal_refs: List[dict]           # v2: 법령/판례 근거

    # 4. 질문 유형 판단 결과
    question_type: str
    need_general_answer: bool
    need_memory: bool
    need_rag: bool
    need_task_extract: bool          # v1 호환용
    need_legal_analysis: bool        # v2
    need_task_generate: bool         # v2
    need_case_card: bool             # v2

    # 5. 법률 분석 결과
    legal_issues: List[str]
    risk_clauses: List[dict]
    missing_checks: List[str]
    recommendations: List[str]

    # 6. LLM / 업무 추출 결과
    summary: Optional[str]
    tasks: List[dict]                # v1 호환용
    action_items: List[dict]         # v2: 법률 할일 생성 결과
    final_answer: Optional[str]

    # 7. 사건 카드
    case_card: Optional[dict]
    case_summary: Optional[str]

    # 8. Graph / 오류 결과
    graph_data: Optional[dict]
    current_step: Optional[str]
    error: Optional[str]