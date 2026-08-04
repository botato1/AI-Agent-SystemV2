# backend/schemas/chat_schema.py

"""
기존 채팅 요청·응답, 채팅방 메시지, 파일 연결,
개인 AI Chat 관련 Pydantic 스키마를 정의한다.

TODO:
- 아래 Legacy 블록은 기존 채팅 라우터와 서비스가 참조하고 있으므로
  마이그레이션 완료 전까지 유지한다.
- 기존 conversations/messages 기반 채팅 기능을
  rooms/room_messages 기반 구조로 교체한 후 Legacy 블록을 삭제한다.
- room_messages는 모순 감지 대상이지만 RAG 소스로
  ChromaDB에 저장하지 않는다.
- 신규 채팅 및 AI Chat API의 생성·수정·조회 스키마는
  관련 라우터 구현 시 별도로 정의한다.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from backend.schemas.common_schema import (
    ORMBaseSchema,
    SoftDeleteSchema,
    TimestampSchema,
)
from backend.schemas.type_schema import (
    AIChatRole,
    AIMessageSourceType,
    FileAnalysisStatus,
    FileKind,
    RoomMessageType,
)


# =============================================================================
# Legacy: 기존 채팅 요청·응답 스키마
# =============================================================================

RequestType = Literal[
    "chat",
    "rag_search",
    "legal_analysis",
    "legal_task_generate",
    "case_card_generate",
]


class ChatRequest(BaseModel):
    """기존 프론트엔드에서 메인 채팅 API로 전달하는 요청."""

    # 기존 conversation 기반 채팅방 ID
    conversation_id: Optional[str] = None

    # 이전 room_id 호환 필드
    room_id: Optional[str] = None

    content: str

    # 기존 프론트엔드 및 서비스 호환을 위해 str로 유지
    source: str = "text"

    # 값이 없으면 기존 classifier 노드에서 분류
    request_type: Optional[RequestType] = None

    target_document_id: Optional[str] = None
    target_filename: Optional[str] = None
    target_document_ids: Optional[List[str]] = None


class ChatMessageSchema(BaseModel):
    """기존 대화 기록에 포함되는 메시지의 최소 구조."""

    message_id: Optional[str] = None
    role: str
    content: str
    created_at: Optional[str] = None


# 기존 코드의 MessageSchema import 호환을 위해 유지
MessageSchema = ChatMessageSchema


class ChatMessage(BaseModel):
    """기존 DB에 저장되거나 조회되는 채팅 메시지 구조."""

    message_id: str
    conversation_id: str
    room_id: Optional[str] = None

    role: str
    content: str
    created_at: str


class ChatHistoryResponse(BaseModel):
    """기존 대화 기록 조회 응답."""

    conversation_id: str
    room_id: Optional[str] = None

    messages: List[ChatMessageSchema] = Field(
        default_factory=list,
    )


class ConversationSchema(BaseModel):
    """기존 채팅방 세션 구조."""

    conversation_id: str
    room_id: Optional[str] = None

    title: str
    created_at: str
    updated_at: str

    document_id: Optional[str] = None
    filename: Optional[str] = None


class ConversationListResponse(BaseModel):
    """기존 채팅방 목록 응답."""

    conversations: List[ConversationSchema] = Field(
        default_factory=list,
    )


class ConversationTitleUpdateRequest(BaseModel):
    """기존 채팅방 제목 수정 요청."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()

        if not title:
            raise ValueError("제목은 공백일 수 없습니다.")

        return title


# =============================================================================
# Re:Call: room_messages
# =============================================================================

class RoomMessageSchema(SoftDeleteSchema):
    """
    채팅 메시지, AI Bot 메시지, 회의 알림, 모순 알림,
    시스템 메시지 하나를 표현한다.

    room_messages 테이블에는 updated_at 컬럼이 없으므로
    created_at만 직접 선언한다.

    AI Bot 및 시스템 메시지는 sender_user_id가 NULL일 수 있다.
    채팅 메시지는 모순 감지 대상이지만 RAG 검색 자료는 아니다.
    """

    id: UUID
    room_id: UUID
    sender_user_id: Optional[UUID] = None

    message_type: RoomMessageType
    content: str = Field(
        ...,
        min_length=1,
    )

    reply_to_id: Optional[UUID] = None

    is_edited: bool
    edited_at: Optional[datetime] = None

    created_at: datetime


# =============================================================================
# Re:Call: room_file_links
# =============================================================================

class RoomFileLinkSchema(ORMBaseSchema):
    """
    파일과 채팅방의 연결 정보를 표현한다.

    파일 원본은 workspace_files에 한 번만 저장하고,
    채팅방에는 연결 정보만 저장한다.

    DB 제약조건:

        UNIQUE(room_id, file_id)
    """

    id: UUID
    room_id: UUID
    file_id: UUID

    upload_message_id: Optional[UUID] = None
    analysis_message_id: Optional[UUID] = None

    linked_by: UUID
    created_at: datetime

# =============================================================================
# Re:Call: room_messages / room_file_links API 요청/응답
# =============================================================================

class RoomMessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    reply_to_id: Optional[UUID] = None


class RoomFileLinkRequest(BaseModel):
    file_id: UUID


class RoomFileResponse(ORMBaseSchema):
    """room에 연결된 파일 정보. 저장 경로 등 내부 정보는 제외하고 노출 가능한 필드만 포함."""

    id: UUID
    original_filename: str
    file_kind: FileKind
    analysis_status: FileAnalysisStatus
    created_at: datetime


class RoomFileListResponse(BaseModel):
    files: list[RoomFileResponse] = Field(default_factory=list)


# =============================================================================
# Re:Call: ai_chat_sessions
# =============================================================================

class AIChatSessionSchema(TimestampSchema, SoftDeleteSchema):
    """
    채팅방 안에서 사용자별로 여러 개 생성 가능한 개인 AI Chat 세션(대화)을 표현한다.
    같은 (workspace_id, room_id, user_id) 조합으로 여러 세션이 존재할 수 있다.
    """

    id: UUID
    workspace_id: UUID
    room_id: Optional[UUID] = None
    user_id: UUID

    title: Optional[str] = Field(
        default=None,
        max_length=200,
    )

class AIChatSessionListResponse(BaseModel):
    sessions: list[AIChatSessionSchema] = Field(default_factory=list)


# =============================================================================
# Re:Call: ai_chat_messages
# =============================================================================

class AIChatMessageSchema(ORMBaseSchema):
    """
    AI Chat 세션에 저장되는 사용자 질문, AI 답변,
    시스템 메시지 하나를 표현한다.

    ai_chat_messages 테이블에는 updated_at이 없으므로
    created_at만 직접 선언한다.
    """

    id: UUID
    session_id: UUID

    role: AIChatRole
    content: str = Field(
        ...,
        min_length=1,
    )

    model_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    created_at: datetime


# =============================================================================
# Re:Call: ai_message_sources
# =============================================================================

class AIMessageSourceSchema(ORMBaseSchema):
    """
    AI 답변에 사용된 근거 자료 하나를 표현한다.

    source_type에 따라 chunk_id/code_fact_id/decision_id 중 하나만 사용한다.
    decision은 workspace_files에 속하지 않으므로 file_id가 NULL이다.
    """

    id: UUID
    ai_message_id: UUID

    source_type: AIMessageSourceType
    file_id: Optional[UUID] = None

    chunk_id: Optional[UUID] = None
    code_fact_id: Optional[UUID] = None
    decision_id: Optional[UUID] = None

    similarity_score: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )
    display_order: int = Field(
        ...,
        ge=0,
    )

    created_at: datetime

    @model_validator(mode="after")
    def _validate_source_consistency(self) -> "AIMessageSourceSchema":
        if self.source_type == "content_chunk":
            if self.file_id is None or self.chunk_id is None:
                raise ValueError(
                    "source_type이 content_chunk이면 "
                    "file_id/chunk_id가 필수입니다."
                )

            if self.code_fact_id is not None or self.decision_id is not None:
                raise ValueError(
                    "source_type이 content_chunk이면 "
                    "code_fact_id/decision_id는 NULL이어야 합니다."
                )

        elif self.source_type == "code_fact":
            if self.file_id is None or self.code_fact_id is None:
                raise ValueError(
                    "source_type이 code_fact이면 "
                    "file_id/code_fact_id가 필수입니다."
                )

            if self.chunk_id is not None or self.decision_id is not None:
                raise ValueError(
                    "source_type이 code_fact이면 "
                    "chunk_id/decision_id는 NULL이어야 합니다."
                )

        elif self.source_type == "decision":
            if self.decision_id is None:
                raise ValueError(
                    "source_type이 decision이면 "
                    "decision_id가 필수입니다."
                )

            if self.file_id is not None or self.chunk_id is not None or self.code_fact_id is not None:
                raise ValueError(
                    "source_type이 decision이면 "
                    "file_id/chunk_id/code_fact_id는 NULL이어야 합니다."
                )

        return self
    
# =============================================================================
# Re:Call: ai_chat API 요청/응답
# =============================================================================

class AIChatMessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class AIChatMessageListResponse(BaseModel):
    messages: list[AIChatMessageSchema] = Field(default_factory=list)


class AIMessageSourceListResponse(BaseModel):
    sources: list[AIMessageSourceSchema] = Field(default_factory=list)