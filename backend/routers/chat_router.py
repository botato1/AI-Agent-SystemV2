# backend/routers/chat_router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id
from backend.db.session import get_db
from backend.db.crud import room_crud, workspace_crud
from backend.schemas.chat_schema import RoomMessageSchema
from backend.schemas.workspace_schema import RoomResponse, RoomListResponse


router = APIRouter(prefix="/api/workspaces/{workspace_id}/rooms", tags=["Rooms"])


class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class RoomUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class RoomMessageListResponse(BaseModel):
    messages: list[RoomMessageSchema] = Field(default_factory=list)


def _require_workspace_member(db: Session, workspace_id: UUID, user_id: str):
    workspace = workspace_crud.get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    membership = workspace_crud.get_membership(db, workspace_id, UUID(user_id))
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="워크스페이스 접근 권한이 없습니다.",
        )

    return workspace


def _get_room_or_404(db: Session, room_id: UUID, workspace_id: UUID):
    room = room_crud.get_room_by_id(db, room_id, workspace_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방을 찾을 수 없습니다.",
        )
    return room


# 채팅방 생성
@router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(
    workspace_id: UUID,
    request: RoomCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_workspace_member(db, workspace_id, current_user_id)

    category = room_crud.get_default_category(db, workspace_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="워크스페이스의 기본 카테고리를 찾을 수 없습니다.",
        )

    room = room_crud.create_room(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        name=request.name,
        created_by=UUID(current_user_id),
    )
    return RoomResponse.model_validate(room)


# 채팅방 목록 조회
@router.get("", response_model=RoomListResponse)
def list_rooms(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_workspace_member(db, workspace_id, current_user_id)

    rooms = room_crud.list_rooms(db, workspace_id)
    return RoomListResponse(rooms=[RoomResponse.model_validate(r) for r in rooms])


# 채팅방 단건 조회
@router.get("/{room_id}", response_model=RoomResponse)
def get_room(
    workspace_id: UUID,
    room_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_workspace_member(db, workspace_id, current_user_id)
    room = _get_room_or_404(db, room_id, workspace_id)
    return RoomResponse.model_validate(room)


# 채팅방 이름 수정
@router.patch("/{room_id}", response_model=RoomResponse)
def update_room(
    workspace_id: UUID,
    room_id: UUID,
    request: RoomUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    room = room_crud.update_room_name(db, room_id, request.name)
    return RoomResponse.model_validate(room)


# 채팅방 삭제
@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(
    workspace_id: UUID,
    room_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    room_crud.delete_room(db, room_id)


# 채팅방 메시지 조회
@router.get("/{room_id}/messages", response_model=RoomMessageListResponse)
def get_room_messages(
    workspace_id: UUID,
    room_id: UUID,
    limit: int = 50,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    messages = room_crud.get_recent_messages(db, room_id, limit=limit)
    return RoomMessageListResponse(
        messages=[RoomMessageSchema.model_validate(m) for m in messages]
    )


# 메시지 삭제
@router.delete("/{room_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room_message(
    workspace_id: UUID,
    room_id: UUID,
    message_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    _require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    message = room_crud.get_message_by_id(db, message_id)
    if not message or message.room_id != room_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="메시지를 찾을 수 없습니다.",
        )

    room_crud.delete_message(db, message_id)