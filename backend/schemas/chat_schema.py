# backend/schemas/chat_schema.py

from typing import List, Optional, Literal

from pydantic import BaseModel, Field


# 프론트 -> 백엔드로 보내는 요청 타입
RequestType = Literal[
    "chat",
    "rag_search",
    "legal_analysis",
    "legal_task_generate",
    "case_card_generate",
]


# React가 사용자의 채팅 메시지를 FastAPI로 보낼 때 사용하는 요청 구조
class ChatRequest(BaseModel):
    # v2 기준 사건방 ID
    conversation_id: Optional[str] = None

    # v1 호환용 채팅방 ID
    room_id: Optional[str] = None

    content: str

    # v1 호환을 위해 str 유지
    # 기존 프론트/서비스에서 text 외 다른 값을 보내도 바로 422가 나지 않게 한다.
    source: str = "text"

    # v2 요청 타입
    # 없으면 classifier_node에서 분류하면 됨
    request_type: Optional[RequestType] = None

    # 프론트에서 선택한 문서 식별값
    target_document_id: Optional[str] = None
    target_filename: Optional[str] = None
    target_document_ids: Optional[List[str]] = None


# 대화 기록 안에 들어가는 메시지 하나의 최소 구조
class ChatMessageSchema(BaseModel):
    message_id: Optional[str] = None
    role: str
    content: str
    created_at: Optional[str] = None


# v1 호환용 별칭
# 기존 코드가 MessageSchema를 import하고 있을 수 있으므로 유지
MessageSchema = ChatMessageSchema


# DB에 저장되거나 DB에서 조회되는 메시지의 구조
class ChatMessage(BaseModel):
    message_id: str

    # v2 기준 사건방 ID
    conversation_id: str

    # v1 호환용 채팅방 ID
    room_id: Optional[str] = None

    role: str
    content: str
    created_at: str


# 이전 대화 기록을 React 또는 LangGraph에 반환할 때 쓰는 구조
class ChatHistoryResponse(BaseModel):
    # v2 기준 사건방 ID
    conversation_id: str

    # v1 호환용 채팅방 ID
    room_id: Optional[str] = None

    messages: List[ChatMessageSchema] = Field(default_factory=list)


# 채팅방 세션 구조
class ConversationSchema(BaseModel):
    # v2 기준 사건방 ID
    conversation_id: str

    # v1 호환용 채팅방 ID
    room_id: Optional[str] = None

    title: str
    created_at: str
    updated_at: str

    # 문서 연결 정보
    document_id: Optional[str] = None
    filename: Optional[str] = None


# 채팅방 목록 응답 구조
class ConversationListResponse(BaseModel):
    conversations: List[ConversationSchema] = Field(default_factory=list)