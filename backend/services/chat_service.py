import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.schemas.chat_schema import ChatRequest
from backend.schemas.response_schema import ChatResponseSchema
from backend.schemas.agent_schema import AgentState
from backend.schemas.type_schema import DEFAULT_QUESTION_TYPE
from backend.graphs.agent_graph import agent_graph


# TODO: 아래 함수들은 legacy conversation 기반 crud로, 새 도메인(rooms/room_messages)
# 으로 마이그레이션되지 않았다. AI Chat 그래프(ai_chat_state.py) 노드 구현 시
# room_crud/content_chunk_crud 기반 실제 로직으로 교체해야 한다.
# 지금은 import 에러만 막아두는 임시 스텁이며 호출 시 의도적으로 실패한다.
# 참고: 현재 이 파일(handle_chat)을 호출하는 곳이 없어 당장 서버 실행에는
# 영향을 주지 않는다.

def _not_implemented(name: str):
    raise NotImplementedError(f"{name}은 아직 새 도메인으로 마이그레이션되지 않았습니다.")


def insert_message(*args, **kwargs):
    _not_implemented("insert_message")


def get_messages(*args, **kwargs):
    _not_implemented("get_messages")


def get_documents(*args, **kwargs):
    _not_implemented("get_documents")


def get_conversation_by_id(*args, **kwargs):
    _not_implemented("get_conversation_by_id")


def create_conversation(*args, **kwargs):
    _not_implemented("create_conversation")


# 상수

STATUS_MAP = {
    "todo": "todo", "할일": "todo", "할 일": "todo",
    "대기": "todo", "예정": "todo", "미완료": "todo",
    "해야함": "todo", "해야 함": "todo",
    "in_progress": "in_progress", "doing": "in_progress",
    "진행중": "in_progress", "진행 중": "in_progress",
    "진행": "in_progress", "작업중": "in_progress", "작업 중": "in_progress",
    "done": "done", "완료": "done", "끝남": "done",
    "완료됨": "done", "처리완료": "done", "처리 완료": "done",
    "delayed": "delayed", "지연": "delayed", "연기": "delayed",
    "늦어짐": "delayed", "보류": "delayed",
}

PRIORITY_MAP = {
    "high": "high", "높음": "high", "상": "high", "긴급": "high", "중요": "high",
    "medium": "medium", "보통": "medium", "중간": "medium", "중": "medium", "일반": "medium",
    "low": "low", "낮음": "low", "하": "low", "여유": "low",
}


# numpy 타입을 Python 기본 타입으로 변환
def to_json_safe(value):
    try:
        import numpy as np

        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.ndarray):
            return value.tolist()

    except ImportError:
        pass

    if isinstance(value, dict):
        return {key: to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe(item) for item in value]

    return value


# DB에서 가져온 메시지를 AgentState용 dict 리스트로 변환
def normalize_messages_for_state(messages: list | None) -> list[dict]:
    if not messages:
        return []

    normalized = []

    for message in messages:
        if isinstance(message, dict):
            normalized.append({
                "role": message.get("role"),
                "content": message.get("content"),
                "created_at": message.get("created_at"),
            })
        else:
            try:
                normalized.append({
                    "role": message["role"],
                    "content": message["content"],
                    "created_at": message["created_at"] if "created_at" in message.keys() else None,
                })
            except Exception:
                continue

    return normalized


# 한글 상태값을 ChatResponseSchema 허용값으로 변환
def normalize_task_status(status: str | None) -> str:
    if not status:
        return "todo"

    return STATUS_MAP.get(str(status).strip(), "todo")


# 한글 우선순위값을 ChatResponseSchema 허용값으로 변환
def normalize_task_priority(priority: str | None) -> str:
    if not priority:
        return "medium"

    return PRIORITY_MAP.get(str(priority).strip(), "medium")


# LLM이 한국어 조사까지 담당자 이름으로 추출한 경우 보정
def normalize_assignee_name(assignee: str | None) -> str | None:
    if not assignee:
        return None

    assignee = str(assignee).strip()

    if not assignee:
        return None

    if "," in assignee or "/" in assignee or " " in assignee:
        return assignee

    if assignee.endswith("이") and len(assignee) >= 3:
        assignee = assignee[:-1]

    return assignee


# sources를 ChatResponseSchema의 SourceSchema 형식으로 변환
def normalize_sources(sources: list | None) -> list[dict]:
    if not sources:
        return []

    normalized = []

    for idx, source in enumerate(sources):
        if isinstance(source, dict):
            normalized.append({
                "id": source.get("id") or source.get("document_id") or source.get("chroma_id") or f"source_{idx + 1}",
                "source": source.get("source") or source.get("filename") or source.get("title") or "unknown",
                "title": source.get("title") or source.get("filename") or source.get("source") or f"source_{idx + 1}",
                "score": to_json_safe(source.get("score")),
            })
        elif isinstance(source, str):
            normalized.append({
                "id": f"source_{idx + 1}",
                "source": source,
                "title": source,
                "score": None,
            })

    return normalized


# tasks를 ChatResponseSchema 형식으로 변환하고 한글 status/priority를 영어로 변환
def normalize_tasks(tasks: list | None) -> list[dict]:
    if not tasks:
        return []

    normalized = []

    for idx, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue

        conversation_id = task.get("conversation_id") or task.get("room_id")

        normalized.append({
            "task_id": task.get("task_id") or task.get("id") or f"task_{idx + 1}",
            "task": task.get("task") or task.get("title") or task.get("content") or "",
            "assignee": normalize_assignee_name(task.get("assignee")),
            "deadline": task.get("deadline") or task.get("due_date") or task.get("due"),
            "status": normalize_task_status(task.get("status")),
            "priority": normalize_task_priority(task.get("priority")),

            # TODO: v1 호환용, 추후 room_id 제거 예정
            "room_id": conversation_id,

            "conversation_id": conversation_id,
            "document_id": task.get("document_id"),
            "created_at": task.get("created_at"),
        })

    return normalized


# 요청에서 conversation_id를 결정
# v2 conversation_id를 우선 사용하고, 없으면 v1 room_id를 사용한다.
def resolve_conversation_id(request: ChatRequest) -> str | None:
    return request.conversation_id or request.room_id


# 프론트 요청에서 target_document_id와 target_filename을 결정
def _resolve_target_document(request: ChatRequest) -> tuple[str | None, str | None]:
    return request.target_document_id, request.target_filename


# AgentState를 프론트 응답 형식으로 변환
def build_chat_response(state: AgentState) -> ChatResponseSchema:
    retrieved_docs = state.get("retrieved_docs") or []
    conversation_id = state.get("conversation_id") or state.get("room_id") or ""

    graph_data = {
        "current_step": state.get("current_step"),
        "question_type": state.get("question_type"),
        "need_general_answer": state.get("need_general_answer"),
        "need_memory": state.get("need_memory"),
        "need_rag": state.get("need_rag"),
        "need_task_extract": state.get("need_task_extract"),
        "need_legal_analysis": state.get("need_legal_analysis"),
        "need_task_generate": state.get("need_task_generate"),
        "need_case_card": state.get("need_case_card"),
        "need_user_documents": state.get("need_user_documents"),
        "need_legal_corpus": state.get("need_legal_corpus"),
        "target_document_id": state.get("target_document_id"),
        "target_filename": state.get("target_filename"),
        "rag_filter": state.get("rag_filter"),
        "low_confidence": state.get("low_confidence"),
        "retrieved_docs_count": len(retrieved_docs),
        "legal_refs_count": len(state.get("legal_refs") or []),
    }

    return ChatResponseSchema(
        # TODO: v1 호환용, 추후 room_id 제거 예정
        room_id=conversation_id,

        conversation_id=conversation_id,
        answer=state.get("final_answer") or "",
        summary=state.get("summary"),
        tasks=to_json_safe(normalize_tasks(state.get("tasks", []))),
        sources=to_json_safe(normalize_sources(state.get("sources", []))),
        graph_data=to_json_safe(graph_data),
        error=state.get("error"),
    )


# AgentState를 LangGraph에 전달해서 실행
def run_agent_graph(state: AgentState) -> AgentState:
    return agent_graph.invoke(state)


# AgentState 초기화
def create_initial_state(
    request: ChatRequest,
    user_id: str,
    conversation_id: str | None = None,
    messages: list | None = None,
) -> AgentState:
    resolved_conversation_id = conversation_id or resolve_conversation_id(request)

    target_document_id, target_filename = _resolve_target_document(request)
    target_document_ids = request.target_document_ids or []

    documents = get_documents(resolved_conversation_id, user_id) if resolved_conversation_id else []

    base_filter = {
        "user_id": str(user_id),
    }

    if target_document_id:
        rag_filter = {
            **base_filter,
            "document_id": target_document_id,
        }
    elif target_filename:
        rag_filter = {
            **base_filter,
            "filename": target_filename,
        }
    elif target_document_ids:
        rag_filter = {
            **base_filter,
            "document_ids": target_document_ids,
        }
    elif documents and resolved_conversation_id:
        rag_filter = {
            **base_filter,

            # TODO: v1 호환용, 추후 room_id 제거 예정
            "room_id": resolved_conversation_id,

            "conversation_id": resolved_conversation_id,
        }
    else:
        rag_filter = base_filter

    document_ids = [
        doc.get("id") or doc.get("document_id")
        for doc in documents
        if isinstance(doc, dict) and (doc.get("id") or doc.get("document_id"))
    ]

    return {
        # 1. 기본 요청 정보
        "user_id": str(user_id),

        # TODO: v1 호환용, 추후 room_id 제거 예정
        "room_id": resolved_conversation_id,

        "conversation_id": resolved_conversation_id,
        "user_message": request.content,
        "source": request.source,
        "created_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "messages": normalize_messages_for_state(messages),

        # 2. 문서 / STT 파일 처리 결과
        "document_json": None,
        "target_document_id": target_document_id,
        "target_filename": target_filename,
        "target_document_ids": target_document_ids,
        "document_ids": document_ids,
        "document_context": documents or [],
        "document_type": None,
        "contract_clauses": [],

        # 3. 이전 대화 / RAG 검색 결과
        "memory_context": None,
        "save_target_content": None,
        "rag_context": None,
        "rag_search_result": None,
        "rag_query": request.content,
        "rag_filter": rag_filter,
        "retrieved_docs": [],
        "low_confidence": False,
        "sources": [],
        "legal_refs": [],

        # 4. 질문 유형 판단 결과
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

        # 5. 법률 분석 결과
        "legal_issues": [],
        "risk_clauses": [],
        "missing_checks": [],
        "recommendations": [],

        # 6. LLM / 업무 추출 결과
        "summary": None,
        "tasks": [],
        "action_items": [],
        "final_answer": None,

        # 7. 사건 카드
        "case_card": None,
        "case_summary": None,
        "case_card_requested": False,

        # 8. Graph / 오류 결과
        "graph_data": None,
        "current_step": "chat_service",
        "error": None,
    }


# 채팅 처리
# 채팅 요청을 처리하고 최종 응답을 반환
async def handle_chat(request: ChatRequest, user_id: str) -> ChatResponseSchema:
    conversation_id = resolve_conversation_id(request)

    # conversation_id가 있으면 현재 사용자의 채팅방인지 먼저 확인
    if conversation_id:
        conversation = get_conversation_by_id(conversation_id, user_id)

        if not conversation:
            raise PermissionError

    # conversation_id가 없으면 신규 대화로 보고 서버에서 새 채팅방 생성
    else:
        conversation_id = create_conversation(
            title=(request.content or "새 채팅")[:30],
            user_id=user_id,
        )

    try:
        insert_message(
            conversation_id=conversation_id,
            role="user",
            content=request.content,
            user_id=user_id,
        )
    except PermissionError:
        raise

    messages = get_messages(conversation_id, user_id)

    state = create_initial_state(
        request=request,
        user_id=user_id,
        conversation_id=conversation_id,
        messages=messages,
    )

    result_state = await asyncio.to_thread(run_agent_graph, state)

    answer = result_state.get("final_answer") or "응답을 생성하지 못했습니다."

    insert_message(
        conversation_id=conversation_id,
        role="assistant",
        content=answer,
        user_id=user_id,
    )

    # 그래프 결과에서 식별자가 누락되더라도 응답에는 현재 conversation_id를 보장
    result_state["conversation_id"] = conversation_id
    result_state["room_id"] = conversation_id

    return build_chat_response(result_state)