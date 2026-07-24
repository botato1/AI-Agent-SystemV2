# backend/schemas/document_schema.py

"""
문서 처리 결과와 문서 분석 결과에 관련된 Pydantic 스키마를 정의한다.

TODO:
- 아래 Legacy 블록은 8003 문서 처리 서비스 연동과 기존 문서 업로드
  라우터에서 참조하고 있으므로 마이그레이션 완료 전까지 유지한다.
- 문서 업로드와 조회 기능을 WorkspaceFileSchema 및
  DocumentAnalysisSchema 기반으로 교체한 후 Legacy 블록을 삭제한다.
- OCR 성공률은 별도 컬럼으로 저장하지 않고 서비스 계층에서 계산한다.
- ocr_required_pages가 0이면 OCR 성공률을 계산하지 않고
  "OCR 미사용" 또는 "N/A"로 표시한다.
"""

from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common_schema import TimestampSchema
from backend.schemas.type_schema import (
    DEFAULT_DOCUMENT_TYPE,
    DocumentFigureType,
    DocumentType,
    FileAnalysisStatus,
)

# =============================================================================
# Legacy: 기존 문서 처리 결과 스키마
# =============================================================================

DocumentSource = Literal[
    "text",
    "pdf",
    "docx",
    "md",
    "image",
]

DocumentStatus = Literal[
    "uploaded",
    "processing",
    "processed",
    "error",
]


class ChunkSchema(BaseModel):
    """기존 문서 처리 결과에 포함되는 RAG 검색용 청크."""

    chunk_id: str
    page_number: int
    content_type: str
    content: str

    # 기존 법률 문서 조항 분석용 필드
    clause: Optional[str] = None
    clause_title: Optional[str] = None


class DocumentMetadata(BaseModel):
    """기존 문서 처리 결과에 포함되는 분석 메타데이터."""

    confidence_score: float
    engines: list[str]
    fallback_used: bool
    page_count: int


class DocumentResultSchema(BaseModel):
    """기존 문서 처리 서비스의 최종 처리 결과."""

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


class DocumentMetadataSaveRequest(BaseModel):
    """8003 문서 처리 결과를 기존 메인 서버에 저장하기 위한 요청."""

    document_id: str = Field(
        ...,
        min_length=1,
    )

    # 기존 conversation 기반 문서 연결 필드
    conversation_id: Optional[str] = Field(
        default=None,
        min_length=1,
    )

    # 이전 room_id 호환 필드
    room_id: Optional[str] = Field(
        default=None,
        min_length=1,
    )

    filename: str = Field(
        ...,
        min_length=1,
    )
    type: DocumentType = DEFAULT_DOCUMENT_TYPE

    file_path: Optional[str] = None
    json_path: Optional[str] = None

    content_markdown: Optional[str] = None
    summary: Optional[str] = None

    page_count: Optional[int] = None
    confidence_score: Optional[float] = None


# =============================================================================
# Re:Call: document_analyses
# =============================================================================

class DocumentAnalysisSchema(TimestampSchema):
    """
    일반 문서 또는 이미지 파일의 분석 결과를 표현한다.

    적용 대상:
        workspace_files.file_kind = "document"
        workspace_files.file_kind = "image"

    file_id는 workspace_files.id를 참조하며 파일당 분석 결과 하나만
    존재할 수 있도록 DB에서 UNIQUE 제약을 적용한다.

    서비스 계층에서 다음 규칙을 검증해야 한다.

        ocr_success_pages <= ocr_required_pages

    ocr_required_pages가 0이면 OCR을 사용하지 않은 것으로 처리한다.
    """

    id: UUID
    file_id: UUID

    extracted_text: Optional[str] = None
    summary: Optional[str] = None

    page_count: Optional[int] = Field(
        default=None,
        ge=0,
    )

    ocr_avg_confidence: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )
    ocr_required_pages: int = Field(
        ...,
        ge=0,
    )
    ocr_success_pages: int = Field(
        ...,
        ge=0,
    )

    table_count: int = Field(
        ...,
        ge=0,
    )
    graph_count: int = Field(
        ...,
        ge=0,
    )
    diagram_count: int = Field(
        ...,
        ge=0,
    )

    processing_duration_ms: Optional[int] = Field(
        default=None,
        ge=0,
    )

    analysis_status: FileAnalysisStatus
    processing_error: Optional[str] = None

    model_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )

# =============================================================================
# Re:Call: document_figures
# =============================================================================

class DocumentFigureSchema(BaseModel):
    """문서에서 감지된 표/차트/다이어그램 크롭 이미지 참조 하나를 표현한다."""

    figure_id: UUID
    page_number: int = Field(..., ge=1)
    type: DocumentFigureType
    image_url: str


class DocumentFigureListResponse(BaseModel):
    figures: list[DocumentFigureSchema] = Field(default_factory=list)