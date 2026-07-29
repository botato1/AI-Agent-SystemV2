# backend/routers/ai_chat_router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import ai_chat_crud, room_crud
from backend.graphs.ai_chat_graph import run_ai_chat_answer
from backend.schemas.chat_schema import (
    AIChatSessionSchema,
    AIChatMessageSchema,
    AIChatMessageCreateRequest,
    AIChatMessageListResponse,
    AIMessageSourceSchema,
    AIMessageSourceListResponse,
)

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat",
    tags=["AI Chat"],
)
standalone_router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/ai-chat",
    tags=["AI Chat"],
)

def _get_room_or_404(db: Session, room_id: UUID, workspace_id: UUID):
    room = room_crud.get_room_by_id(db, room_id, workspace_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방을 찾을 수 없습니다.",
        )
    return room


# 세션 조회/생성
@router.get("/session", response_model=AIChatSessionSchema)
def get_or_create_ai_chat_session(
    workspace_id: UUID,
    room_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    session = ai_chat_crud.get_or_create_session(db, workspace_id, room_id, UUID(current_user_id))
    return AIChatSessionSchema.model_validate(session)


# 질문 전송 (AI 답변 생성)
@router.post("/messages", response_model=AIChatMessageSchema, status_code=status.HTTP_201_CREATED)
def send_ai_chat_message(
    workspace_id: UUID,
    room_id: UUID,
    request: AIChatMessageCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    room = _get_room_or_404(db, room_id, workspace_id)

    session = ai_chat_crud.get_or_create_session(db, workspace_id, room_id, UUID(current_user_id))

    # 답변 생성 노드에 넘길 대화 이력 — 이번 질문을 저장하기 전 시점의 기록만 사용
    # (저장 후 조회하면 방금 보낸 질문이 "이전 대화"에 중복으로 들어감)
    history_rows = ai_chat_crud.get_session_history(db, session.id)
    chat_history = [
        {"role": m.role, "content": m.content}
        for m in history_rows
        if m.role in ("user", "assistant")
    ]

    result = run_ai_chat_answer(
        session_id=str(session.id),
        workspace_id=str(workspace_id),
        category_id=str(room.category_id),
        room_id=str(room_id),
        user_id=current_user_id,
        user_message=request.content,
        chat_history=chat_history,
    )
    answer = result.get("answer") or "지금은 답변을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."
    sources = result.get("retrieved_sources") or []

    # 답변 생성을 먼저 시도하고 성공했을 때만 메시지를 저장한다.
    # (실패 시 대화기록에 "답변 없는 질문"만 남는 것을 방지)
    assistant_message = ai_chat_crud.add_ai_exchange(
        db,
        session_id=session.id,
        user_content=request.content,
        assistant_content=answer,
        sources=sources,
        model_name=result.get("answer_model_name"),
    )
    return AIChatMessageSchema.model_validate(assistant_message)


# 대화 기록 조회
@router.get("/messages", response_model=AIChatMessageListResponse)
def get_ai_chat_messages(
    workspace_id: UUID,
    room_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    session = ai_chat_crud.get_or_create_session(db, workspace_id, room_id, UUID(current_user_id))
    messages = ai_chat_crud.get_session_history(db, session.id)
    return AIChatMessageListResponse(
        messages=[AIChatMessageSchema.model_validate(m) for m in messages]
    )


# 메시지별 근거자료 조회
@router.get("/messages/{message_id}/sources", response_model=AIMessageSourceListResponse)
def get_ai_chat_message_sources(
    workspace_id: UUID,
    room_id: UUID,
    message_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    result = ai_chat_crud.get_message_with_session(db, message_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="메시지를 찾을 수 없습니다.",
        )

    _, session = result
    if (
        session.workspace_id != workspace_id
        or session.room_id != room_id
        or session.user_id != UUID(current_user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="메시지를 찾을 수 없습니다.",
        )

    sources = ai_chat_crud.get_message_sources(db, message_id)
    return AIMessageSourceListResponse(
        sources=[AIMessageSourceSchema.model_validate(s) for s in sources]
    )

# 세션 조회/생성 (워크스페이스 단독)
@standalone_router.get("/session", response_model=AIChatSessionSchema)
def get_or_create_standalone_ai_chat_session(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    session = ai_chat_crud.get_or_create_session(db, workspace_id, None, UUID(current_user_id))
    return AIChatSessionSchema.model_validate(session)


# 질문 전송 (워크스페이스 단독)
@standalone_router.post("/messages", response_model=AIChatMessageSchema, status_code=status.HTTP_201_CREATED)
def send_standalone_ai_chat_message(
    workspace_id: UUID,
    request: AIChatMessageCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    category = room_crud.get_default_category(db, workspace_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="워크스페이스의 기본 카테고리를 찾을 수 없습니다.",
        )

    session = ai_chat_crud.get_or_create_session(db, workspace_id, None, UUID(current_user_id))

    history_rows = ai_chat_crud.get_session_history(db, session.id)
    chat_history = [
        {"role": m.role, "content": m.content}
        for m in history_rows
        if m.role in ("user", "assistant")
    ]

    result = run_ai_chat_answer(
        session_id=str(session.id),
        workspace_id=str(workspace_id),
        category_id=str(category.id),
        user_id=current_user_id,
        user_message=request.content,
        chat_history=chat_history,
    )
    answer = result.get("answer") or "지금은 답변을 생성할 수 없습니다. 잠시 후 다시 시도해주세요."
    sources = result.get("retrieved_sources") or []

    assistant_message = ai_chat_crud.add_ai_exchange(
        db,
        session_id=session.id,
        user_content=request.content,
        assistant_content=answer,
        sources=sources,
        model_name=result.get("answer_model_name"),
    )
    return AIChatMessageSchema.model_validate(assistant_message)


# 대화 기록 조회 (워크스페이스 단독)
@standalone_router.get("/messages", response_model=AIChatMessageListResponse)
def get_standalone_ai_chat_messages(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    session = ai_chat_crud.get_or_create_session(db, workspace_id, None, UUID(current_user_id))
    messages = ai_chat_crud.get_session_history(db, session.id)
    return AIChatMessageListResponse(
        messages=[AIChatMessageSchema.model_validate(m) for m in messages]
    )


# 메시지별 근거자료 조회 (워크스페이스 단독)
@standalone_router.get("/messages/{message_id}/sources", response_model=AIMessageSourceListResponse)
def get_standalone_ai_chat_message_sources(
    workspace_id: UUID,
    message_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    result = ai_chat_crud.get_message_with_session(db, message_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="메시지를 찾을 수 없습니다.",
        )

    _, session = result
    if (
        session.workspace_id != workspace_id
        or session.room_id is not None
        or session.user_id != UUID(current_user_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="메시지를 찾을 수 없습니다.",
        )

    sources = ai_chat_crud.get_message_sources(db, message_id)
    return AIMessageSourceListResponse(
        sources=[AIMessageSourceSchema.model_validate(s) for s in sources]
    )