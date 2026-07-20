# backend/routers/ai_chat_router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import ai_chat_crud, room_crud
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


def _get_room_or_404(db: Session, room_id: UUID, workspace_id: UUID):
    room = room_crud.get_room_by_id(db, room_id, workspace_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방을 찾을 수 없습니다.",
        )
    return room


# TODO(가동현): RAG 그래프 노드 연결 예정. 지금은 답변 생성 부분만 스텁 처리.
def _generate_ai_response(session_id: UUID, question: str) -> tuple[str, list[dict]]:
    """가동현님의 RAG 그래프 노드가 준비되면 이 함수를 실제 호출로 교체."""
    raise NotImplementedError("AI 답변 생성 그래프가 아직 연결되지 않았습니다.")


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
    _get_room_or_404(db, room_id, workspace_id)

    session = ai_chat_crud.get_or_create_session(db, workspace_id, room_id, UUID(current_user_id))
    ai_chat_crud.add_message(db, session_id=session.id, role="user", content=request.content)

    try:
        answer, sources = _generate_ai_response(session.id, request.content)
    except NotImplementedError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 답변 생성 기능은 아직 사용할 수 없습니다.",
        )

    assistant_message = ai_chat_crud.add_message(db, session_id=session.id, role="assistant", content=answer)
    if sources:
        ai_chat_crud.add_sources(db, assistant_message.id, sources)

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

    sources = ai_chat_crud.get_message_sources(db, message_id)
    return AIMessageSourceListResponse(
        sources=[AIMessageSourceSchema.model_validate(s) for s in sources]
    )