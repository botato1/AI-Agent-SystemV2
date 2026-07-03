# 문서 처리 결과 구조
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from backend.schemas.common_schema import CommonDocumentSchema
from backend.schemas.type_schema import DocumentType, DEFAULT_DOCUMENT_TYPE

DocumentSource = Literal["text", "pdf", "docx", "md", "image"]
DocumentStatus = Literal["uploaded", "processing", "processed", "error"]

# RAG 검색용 청크 하나의 구조
class ChunkSchema(BaseModel):
    chunk_id: str        # 청크 고유 ID
    page_number: int     # 원본 문서 페이지 번호
    content_type: str    # text / table / image / diagram
    content: str         # 청크 내용

    # v2 계약서 조항 분석용
    clause: Optional[str] = None
    clause_title: Optional[str] = None


# 문서 처리 관련 메타데이터
class DocumentMetadata(BaseModel):
    confidence_score: float   # OCR 또는 문서 추출 신뢰도
    engines: List[str]        # 사용된 문서 처리 엔진 목록
    fallback_used: bool       # fallback 사용 여부
    page_count: int           # 전체 페이지 수


# 최종 문서 처리 결과 구조
class DocumentResultSchema(BaseModel):
    id: str
    title: str
    type: DocumentType = DEFAULT_DOCUMENT_TYPE
    source: DocumentSource

    content_markdown: Optional[str] = None
    summary: Optional[str] = None

    chunks: list[ChunkSchema] = Field(default_factory=list)
    metadata: Optional[DocumentMetadata] = None

    created_at: str
    status: DocumentStatus = "processed"
    error: Optional[str] = None


# 문서 메타데이터 저장 요청 구조
class DocumentMetadataSaveRequest(BaseModel):
    document_id: str = Field(..., min_length=1)   # 8003에서 받은 document_id
    room_id: str = Field(..., min_length=1)        # 채팅방 ID
    conversation_id: Optional[str] = None

    filename: str = Field(..., min_length=1)       # 원본 파일명
    type: DocumentType = DEFAULT_DOCUMENT_TYPE

    file_path: Optional[str] = None                # 8003 원본 파일 저장 경로
    json_path: Optional[str] = None                # 8003 JSON 저장 경로

    content_markdown: Optional[str] = None         # 마크다운 형식의 문서 전체 텍스트
    summary: Optional[str] = None                  # 문서 요약

    page_count: Optional[int] = None
    confidence_score: Optional[float] = None