from typing import Optional, TypedDict, List

from backend.schemas.type_schema import QuestionType, DocumentType

class AgentState(TypedDict):
    # 1. 기본 요청 정보
    user_id: Optional[str]
    room_id: str            # v1 호환용 -> v2 기능 안정화 되면 삭제
    conversation_id: str    # 사건방 ID
    user_message: str       # 현재 사용자 입력
    source: str             # 입력 출처: text/file/audio/button 등
    created_at: str
    messages: List[dict]    # 이전 대화

    # 2. 문서 / STT 파일 처리 결과
    document_json: Optional[dict]
    target_document_id: Optional[str]
    target_filename: Optional[str]
    target_document_ids: Optional[List[str]]
    document_ids: List[str]         # 현재 conversation_id에 연결된 전체 문서 ID 목록
    document_context: List[dict]    # conversation_id 기준 문서 메타/컨텍스트 목록
    document_type: Optional[DocumentType]  # v1/v2 혼용 기간 동안 document/meeting/voice도 임시 허용

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
    rag_filter: Optional[dict]      # ChromaDB where 필터: {"document_id": "..."} 또는 {"conversation_id": "..."}
    retrieved_docs: List[dict]
    low_confidence: bool
    sources: List[dict]
    legal_refs: List[dict]          # v2: 법령/판례 근거

    # 4. 질문 유형 판단 결과
    question_type: QuestionType  # 모델1 의도분류 결과 또는 UI 버튼/팝업에서 직접 설정된 작업 타입
    need_general_answer: bool
    need_memory: bool
    need_rag: bool
    need_task_extract: bool         # v1 호환용
    need_legal_analysis: bool       # v2: 법률 분석 필요 여부
    need_task_generate: bool        # v2: 법률 기반 후속 조치/업무 생성 필요 여부
    need_case_card: bool            # v2: 사건카드 생성/업데이트 필요 여부
    need_user_documents: bool       # v2: user_documents 검색 필요 여부
    need_legal_corpus: bool         # v2: legal_corpus 검색 필요 여부

    # 5. 법률 분석 결과
    legal_issues: List[str]
    risk_clauses: List[dict]
    missing_checks: List[str]
    recommendations: List[str]

    # 6. LLM / 업무 추출 결과
    summary: Optional[str]
    tasks: List[dict]               # v1 호환용
    action_items: List[dict]        # v2: 법률 후속 조치/액션 아이템
    final_answer: Optional[str]

    # 7. 사건 카드
    case_card: Optional[dict]
    case_summary: Optional[str]
    case_card_requested: bool       # 사건카드 생성/업데이트 버튼 요청 여부

    # 8. Graph / 오류 결과
    graph_data: Optional[dict]
    current_step: Optional[str]
    error: Optional[str]