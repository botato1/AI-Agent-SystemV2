from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.core.dependencies import get_current_user_id
from backend.schemas.chat_schema import ChatRequest, ChatHistoryResponse
from backend.schemas.response_schema import ChatResponseSchema
from backend.services.chat_service import handle_chat
from backend.db.crud import (
    create_conversation,
    get_conversations,
    get_messages,
    delete_conversation,
    delete_message,
    get_conversation_by_id,
    get_documents,
    delete_all_conversations_and_messages,
    link_document_to_room,
    unlink_document_from_room,
    get_documents_by_room_id,
)


class ConversationCreateRequest(BaseModel):
    title: str = "새 대화"


class ConversationDocumentRequest(BaseModel):
    document_id: str


router = APIRouter(
    prefix="/api",
    tags=["Chat"],
)


def get_conversation_or_404(conversation_id: str, user_id: str):
    conversation = get_conversation_by_id(conversation_id, user_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방을 찾을 수 없습니다.",
        )

    return conversation


# 사용자 채팅 메시지 전송 API
@router.post("/chat", response_model=ChatResponseSchema)
async def send_chat_message(
    request: ChatRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return await handle_chat(request, current_user_id)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방을 찾을 수 없습니다.",
        )


# 특정 채팅방의 이전 대화 기록 조회 API
@router.get("/conversations/{conversation_id}/messages", response_model=ChatHistoryResponse)
def get_chat_history(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    get_conversation_or_404(conversation_id, current_user_id)

    rows = get_messages(conversation_id, current_user_id)

    messages = [
        {
            "message_id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return {
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "messages": messages,
    }


# 새 채팅방을 생성하는 API
@router.post("/conversations")
def create_chat_room(
    request: ConversationCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    conversation_id = create_conversation(
        title=request.title,
        user_id=current_user_id,
    )

    return {
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "title": request.title,
    }


# 전체 채팅방 목록을 조회하는 API
@router.get("/conversations")
def get_chat_rooms(
    current_user_id: str = Depends(get_current_user_id),
):
    rows = get_conversations(current_user_id)

    conversations = [
        {
            "room_id": row["id"],  # TODO: v1 호환용, 추후 제거 예정
            "conversation_id": row["id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "filename": row.get("filename"),
            "document_id": row.get("document_id"),
        }
        for row in rows
    ]

    return {
        "conversations": conversations,
    }


# 모든 채팅방과 메시지 전체 삭제 API
@router.delete("/conversations")
def remove_all_chat_rooms(
    current_user_id: str = Depends(get_current_user_id),
):
    result = delete_all_conversations_and_messages(current_user_id)

    return {
        "status": result.get("status", "success"),
        "message": result.get("message", "모든 채팅방과 메시지가 삭제되었습니다."),
        "error": None,
    }


# 채팅방 단건 조회 API
@router.get("/conversations/{conversation_id}")
def get_conversation_detail(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    row = get_conversation_or_404(conversation_id, current_user_id)

    document_rows = get_documents(conversation_id, current_user_id)

    documents = [
        {
            "document_id": doc["id"],
            "filename": doc["title"],
            "title": doc["title"],
            "type": doc["type"],
            "source": doc["source"],
            "summary": doc["summary"],
            "status": doc["status"],
            "json_path": doc.get("json_path"),
            "created_at": doc["created_at"],
        }
        for doc in document_rows
    ]

    target_document = documents[0] if documents else None

    return {
        "status": "success",
        "room_id": row["id"],  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "target_document_id": target_document["document_id"] if target_document else None,
        "target_filename": target_document["filename"] if target_document else None,
        "documents": documents,
        "error": None,
    }


# 채팅방 삭제 API
@router.delete("/conversations/{conversation_id}")
def remove_chat_room(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    deleted = delete_conversation(conversation_id, current_user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="삭제할 채팅방을 찾을 수 없습니다.",
        )

    return {
        "status": "success",
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "message": "채팅방이 삭제되었습니다.",
        "error": None,
    }


# 메시지 삭제 API
@router.delete("/messages/{message_id}")
def remove_message(
    message_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    deleted = delete_message(message_id, current_user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="삭제할 메시지를 찾을 수 없습니다.",
        )

    return {
        "status": "success",
        "message_id": message_id,
        "message": "메시지가 삭제되었습니다.",
        "error": None,
    }


# 채팅방에 연결된 문서 목록 조회 API
@router.get("/conversations/{conversation_id}/documents")
def get_conversation_documents(
    conversation_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    get_conversation_or_404(conversation_id, current_user_id)

    docs = get_documents_by_room_id(conversation_id, current_user_id)

    return {
        "status": "success",
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "documents": [
            {
                "document_id": doc["id"],
                "title": doc["title"],
                "type": doc["type"],
                "source": doc["source"],
                "chroma_status": doc.get("chroma_status"),
                "created_at": doc["created_at"],
            }
            for doc in docs
        ],
        "error": None,
    }


# 채팅방에 문서 연결 API
@router.post("/conversations/{conversation_id}/documents")
def add_document_to_conversation(
    conversation_id: str,
    request: ConversationDocumentRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    linked = link_document_to_room(
        room_id=conversation_id,
        document_id=request.document_id,
        user_id=current_user_id,
    )

    if not linked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방 또는 문서를 찾을 수 없습니다.",
        )

    return {
        "status": "success",
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "document_id": request.document_id,
        "message": "문서가 채팅방에 연결되었습니다.",
        "error": None,
    }


# 채팅방에서 문서 연결 해제 API
@router.delete("/conversations/{conversation_id}/documents/{document_id}")
def remove_document_from_conversation(
    conversation_id: str,
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    unlinked = unlink_document_from_room(
        room_id=conversation_id,
        document_id=document_id,
        user_id=current_user_id,
    )

    if not unlinked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="연결된 문서를 찾을 수 없습니다.",
        )

    return {
        "status": "success",
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "document_id": document_id,
        "message": "문서 연결이 해제되었습니다.",
        "error": None,
    }