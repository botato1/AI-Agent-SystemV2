# ChromaDB / RAG 관련 구조
from typing import Optional, List, Literal, Any

from pydantic import BaseModel, Field


# v1 - /api/rag/search 라이브 경로 유지
# 이 구조를 바꾸면 /api/rag/search 응답이 비거나 누락될 수 있으므로 유지한다.
class RagSearchItemSchema(BaseModel):
    id: str
    content: str
    source: str

    source_url: Optional[str] = None
    data_type: Optional[str] = None
    importance: Optional[int] = None
    score: Optional[float] = None
    title: Optional[str] = None
    created_at: Optional[str] = None


class RagSearchResponseSchema(BaseModel):
    status: str
    query: str
    count: int

    data: List[RagSearchItemSchema] = Field(default_factory=list)

    error: Optional[str] = None


# v2 - Chroma 저장용 metadata

# v2 최종 목표는 Chroma metadata에 파일명, 의뢰인명, 사건명 같은 민감정보를 넣지 않는 것
# 다만 현재 단계에서는 schema 변경으로 인한 오류를 줄이기 위해 v1 호환용 필드도 Optional로 남겨둔다.
SourceType = Literal[
    "contract",
    "consultation_audio",
    "consultation_note",
    "precedent_ref",
    "evidence",
    "law",
    "precedent",
]


LegalRefType = Literal["law", "precedent"]


class ChromaMetadataSchema(BaseModel):
    # v2 핵심 metadata
    document_id: Optional[str] = None

    conversation_id: Optional[str] = None
    room_id: Optional[str] = None

    type: Optional[SourceType] = None
    source: Optional[str] = None

    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    page_number: Optional[int] = None
    content_type: Optional[str] = None

    # 계약서 조항
    clause: Optional[str] = None

    # 법령/판례 근거
    legal_ref_type: Optional[LegalRefType] = None
    law_name: Optional[str] = None
    article_no: Optional[str] = None
    case_no: Optional[str] = None

    # v1 호환용 metadata
    # 기존 Chroma metadata 또는 기존 코드에서 참조할 가능성이 있는 필드.
    id: Optional[str] = None
    title: Optional[str] = None
    language: Optional[str] = None
    created_at: Optional[str] = None
    status: Optional[str] = None
    chroma_id: Optional[str] = None
    user_edited: Optional[bool] = None

    # v1에서는 ChromaDB 저장 때문에 콤마 문자열로 사용했을 수 있음
    tags: Optional[str] = None

    importance_score: Optional[int] = None

    upload_context: Optional[str] = None
    filename: Optional[str] = None
    notion_url: Optional[str] = None
    error: Optional[str] = None


class ChromaSearchResultSchema(BaseModel):
    # v1 호환을 위해 id는 Optional로 유지
    id: Optional[str] = None

    content: str
    metadata: ChromaMetadataSchema
    score: Optional[float] = None


# Ollama 요청/응답 구조
# v1 필드 유지 + v2 필드 추가
class OllamaRequest(BaseModel):
    user_input: str

    # v1 호환용
    conversation_id: Optional[str] = None
    filter_type: Optional[str] = None

    # v2 추가
    room_id: Optional[str] = None
    target_document_id: Optional[str] = None
    target_document_ids: Optional[list[str]] = None


class OllamaResponse(BaseModel):
    status: str
    original_input: str

    normalized_input: Optional[str] = None
    intent: Optional[str] = None
    answer: Optional[str] = None

    # v1: list[str]
    # v2: list[dict[str, Any]]
    sources: list[str | dict[str, Any]] = Field(default_factory=list)

    error: Optional[str] = None