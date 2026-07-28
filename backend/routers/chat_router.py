# backend/routers/chat_router.py
import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db, SessionLocal
from backend.db.crud import file_crud, room_crud, workspace_crud, notification_crud, contradiction_crud
from backend.graphs.contradiction_graph import run_contradiction_detection
from backend.schemas.chat_schema import (
    RoomMessageSchema,
    RoomMessageCreateRequest,
    RoomFileLinkRequest,
    RoomFileResponse,
    RoomFileListResponse,
)
from backend.schemas.workspace_schema import RoomResponse, RoomListResponse
from backend.services import judgment_service


router = APIRouter(prefix="/api/workspaces/{workspace_id}/rooms", tags=["Rooms"])

# 같은 room에서 메시지가 빠르게 여러 개 오면 모순감지+판단파이프라인이 동시에
# DB 커넥션을 여러 개 물어 풀 고갈이 날 수 있다 (meeting 실시간 경로와 동일 이유).
# room_id 단위로 직렬화해서 방지한다.
_ROOM_PROCESSING_LOCKS: dict[UUID, asyncio.Lock] = {}


def _get_room_processing_lock(room_id: UUID) -> asyncio.Lock:
    lock = _ROOM_PROCESSING_LOCKS.get(room_id)
    if lock is None:
        lock = asyncio.Lock()
        _ROOM_PROCESSING_LOCKS[room_id] = lock
    return lock


def _notify_contradiction_detected(workspace_id: UUID, result: dict, statement_text: str) -> None:
    """채팅 메시지에서 모순이 감지되면 워크스페이스 멤버들에게 알림을 남긴다."""
    detected = result.get("detected_contradictions") or []
    saved_ids = result.get("saved_contradiction_ids") or []
    pair_count = min(len(detected), len(saved_ids))
    if pair_count == 0:
        return

    best_index = max(range(pair_count), key=lambda i: detected[i]["confidence_score"])
    contradiction = detected[best_index]
    contradiction_id = saved_ids[best_index]

    db = SessionLocal()
    try:
        source_name = None
        excerpt = ""
        reference_file_id = contradiction.get("reference_file_id")
        if reference_file_id:
            file = file_crud.get_file(db, UUID(reference_file_id))
            source_name = file.original_filename if file else None

        saved_row = contradiction_crud.get_contradiction(db, UUID(contradiction_id))
        if saved_row and saved_row.reference_text_snapshot:
            excerpt = " ".join(saved_row.reference_text_snapshot.split())[:100]

        if source_name and excerpt:
            display_message = f"'{statement_text}'라고 하셨는데, 기존 자료({source_name})의 '{excerpt}'와 다릅니다."
        elif excerpt:
            display_message = f"'{statement_text}'라고 하셨는데, 기존 자료의 '{excerpt}'와 다릅니다."
        else:
            display_message = f"'{statement_text}'라고 하셨는데, 기존 자료와 다릅니다."

        for member, _user in workspace_crud.list_members(db, workspace_id):
            if not notification_crud.is_notification_enabled(
                db, workspace_id, member.user_id, "contradiction_detected",
            ):
                continue
            notification_crud.create_notification(
                db, user_id=member.user_id, workspace_id=workspace_id,
                type="contradiction_detected", title="모순 감지",
                message=display_message,
                ref_type="contradiction", ref_id=UUID(contradiction_id),
            )
    finally:
        db.close()


async def _process_room_message_analysis(
    room_id: UUID, workspace_id: UUID, category_id: UUID,
    statement_text: str, message_id: str,
) -> None:
    """채팅 메시지 하나의 모순감지+판단파이프라인을 room 단위로 직렬 처리한다."""
    lock = _get_room_processing_lock(room_id)
    async with lock:
        result = await asyncio.to_thread(
            run_contradiction_detection,
            workspace_id=str(workspace_id),
            category_id=str(category_id),
            source_type="room_message",
            statement_text=statement_text,
            room_message_id=message_id,
        )
        await asyncio.to_thread(_notify_contradiction_detected, workspace_id, result, statement_text)

        await asyncio.to_thread(
            judgment_service.run_judgment_pipeline,
            workspace_id=str(workspace_id),
            category_id=str(category_id),
            source_type="room_message",
            statement_text=statement_text,
            room_message_id=message_id,
            session_room_id=str(room_id),
        )

class RoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class RoomUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class RoomMessageListResponse(BaseModel):
    messages: list[RoomMessageSchema] = Field(default_factory=list)


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
    require_workspace_member(db, workspace_id, current_user_id)

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
    require_workspace_member(db, workspace_id, current_user_id)

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
    require_workspace_member(db, workspace_id, current_user_id)
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
    require_workspace_member(db, workspace_id, current_user_id)
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
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    room_crud.delete_room(db, room_id)

# 메시지 전송
@router.post("/{room_id}/messages", response_model=RoomMessageSchema, status_code=status.HTTP_201_CREATED)
def send_room_message(
    workspace_id: UUID,
    room_id: UUID,
    request: RoomMessageCreateRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    room = _get_room_or_404(db, room_id, workspace_id)

    message = room_crud.add_message(
        db,
        room_id=room_id,
        message_type="text",
        content=request.content,
        sender_user_id=UUID(current_user_id),
        reply_to_id=request.reply_to_id,
    )

    # 메시지 저장 후 모순 탐지를 백그라운드로 실행.
    # (RAG 토글 여부와 무관하게 모든 텍스트 메시지 대상 — RAG 토글은 검색 포함 범위이지
    # 모순 탐지 대상 범위는 아니라고 판단. 필요하면 room.rag_enabled 체크 추가)
    statement_text = (request.content or "").strip()
    if statement_text:
        background_tasks.add_task(
            _process_room_message_analysis,
            room_id, workspace_id, room.category_id, statement_text, str(message.id),
        )

    return RoomMessageSchema.model_validate(message)

# 채팅방 메시지 조회
@router.get("/{room_id}/messages", response_model=RoomMessageListResponse)
def get_room_messages(
    workspace_id: UUID,
    room_id: UUID,
    limit: int = 50,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
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
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    message = room_crud.get_message_by_id(db, message_id)
    if not message or message.room_id != room_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="메시지를 찾을 수 없습니다.",
        )

    room_crud.delete_message(db, message_id)

# 파일 연결
@router.post("/{room_id}/files", response_model=RoomFileResponse, status_code=status.HTTP_201_CREATED)
def link_room_file(
    workspace_id: UUID,
    room_id: UUID,
    request: RoomFileLinkRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    workspace_file = file_crud.get_file(db, request.file_id)
    if not workspace_file or workspace_file.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="연결할 파일을 찾을 수 없습니다.",
        )

    file_crud.link_file_to_room(db, room_id, request.file_id, UUID(current_user_id))
    return RoomFileResponse.model_validate(workspace_file)


# 연결된 파일 목록 조회
@router.get("/{room_id}/files", response_model=RoomFileListResponse)
def get_room_files(
    workspace_id: UUID,
    room_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    files = file_crud.list_files_by_room(db, room_id)
    return RoomFileListResponse(files=[RoomFileResponse.model_validate(f) for f in files])


# 파일 연결 해제
@router.delete("/{room_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_room_file(
    workspace_id: UUID,
    room_id: UUID,
    file_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_room_or_404(db, room_id, workspace_id)

    unlinked = file_crud.unlink_file_from_room(db, room_id, file_id)
    if not unlinked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="연결된 파일을 찾을 수 없습니다.",
        )