# backend/schemas/agent_schema.py

"""
기존 LangGraph 에이전트 상태(AgentState)를 정의한다.

TODO:
- 아래 AgentState는 기존 법률 도메인 그래프에서 사용 중이므로
  신규 그래프 마이그레이션 전까지 필드명과 타입을 변경하지 않는다.
- 현재 backend/graphs/agent_graph.py와 graphs/nodes 하위 노드들이
  AgentState를 직접 참조하고 있다.
- Re:Call 신규 그래프 상태는 이 파일에 추가하지 않고
  backend/graphs/states 하위 파일에 기능별로 분리하여 정의한다.

신규 상태 파일 구성:
- common_state.py
- file_analysis_state.py
- contradiction_state.py
- contradiction_resolution_state.py
- meeting_postprocess_state.py
- ai_chat_state.py

신규 그래프 재구성과 노드 교체가 완료되고 기존 AgentState 참조가
모두 제거된 것을 확인한 후, 이 파일과 기존 그래프 노드를 삭제한다.
"""

from typing import List, Optional, TypedDict

from backend.schemas.type_schema import DocumentType, QuestionType


class AgentState(TypedDict):
    # =========================================================================
    # 1. 기본 요청 정보
    # =========================================================================

    user_id: Optional[str]
    conversation_id: Optional[str]  # 기존 대화방 ID
    room_id: Optional[str]          # 이전 코드 호환용
    user_message: str               # 현재 사용자 입력
    source: str                     # text, file, audio, button 등 입력 출처
    created_at: str
    messages: List[dict]            # 이전 대화 기록

    # =========================================================================
    # 2. 문서 및 STT 파일 처리 결과
    # =========================================================================

    document_json: Optional[dict]
    target_document_id: Optional[str]
    target_filename: Optional[str]
    target_document_ids: Optional[List[str]]

    # 현재 conversation_id에 연결된 전체 문서 ID 목록
    document_ids: List[str]

    # conversation_id 기준 문서 메타데이터 및 컨텍스트
    document_context: List[dict]

    # 기존 문서 처리 코드 호환을 위해 유지
    document_type: Optional[DocumentType]

    # 기존 법률 문서 조항 분석 결과
    contract_clauses: List[dict]

    # =========================================================================
    # 3. 이전 대화 및 RAG 검색 결과
    # =========================================================================

    memory_context: Optional[str]
    save_target_content: Optional[str]

    # 기존 rag_node, task_node, ollama_service는 rag_context를 문자열로
    # 처리하므로 관련 노드 마이그레이션 전까지 Optional[str]을 유지한다.
    rag_context: Optional[str]

    # rag_service.retrieve_relevant_knowledge() 반환 결과
    rag_search_result: Optional[dict]

    rag_query: Optional[str]

    # 기존 ChromaDB 검색 필터
    # 예: {"document_id": "..."} 또는 {"conversation_id": "..."}
    rag_filter: Optional[dict]

    retrieved_docs: List[dict]
    low_confidence: bool
    sources: List[dict]

    # 기존 법률 서비스의 법령 및 판례 근거
    legal_refs: List[dict]

    # =========================================================================
    # 4. 질문 유형 판단 결과
    # =========================================================================

    # 기존 분류 모델 또는 UI 요청에서 설정하는 작업 유형
    question_type: QuestionType

    need_general_answer: bool
    need_memory: bool
    need_rag: bool

    # 기존 업무 추출 분기
    need_task_extract: bool

    # 기존 법률 서비스 분기
    need_legal_analysis: bool
    need_task_generate: bool
    need_case_card: bool
    need_user_documents: bool
    need_legal_corpus: bool

    # =========================================================================
    # 5. 기존 법률 분석 결과
    # =========================================================================

    legal_issues: List[str]
    risk_clauses: List[dict]
    missing_checks: List[str]
    recommendations: List[str]

    # =========================================================================
    # 6. LLM 및 업무 추출 결과
    # =========================================================================

    summary: Optional[str]

    # 기존 업무 추출 결과
    tasks: List[dict]

    # 기존 법률 후속 조치 결과
    action_items: List[dict]

    final_answer: Optional[str]

    # =========================================================================
    # 7. 기존 사건 카드
    # =========================================================================

    case_card: Optional[dict]
    case_summary: Optional[str]
    case_card_requested: bool

    # =========================================================================
    # 8. 그래프 실행 및 오류 결과
    # =========================================================================

    graph_data: Optional[dict]
    current_step: Optional[str]
    error: Optional[str]