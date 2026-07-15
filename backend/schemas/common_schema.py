# backend/schemas/common_schema.py

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.type_schema import (
    DEFAULT_DOCUMENT_TYPE,
    DocumentType,
)


# =============================================================================
# Re:Call 공통 스키마
# =============================================================================

# ORM 객체의 속성을 기반으로 Pydantic 모델을 생성할 수 있도록 설정
class ORMBaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# 생성일과 수정일 필드를 제공하는 공통 스키마
class TimestampSchema(ORMBaseSchema):
    created_at: datetime
    updated_at: datetime

# 소프트 삭제 일시 필드를 제공하는 공통 스키마
class SoftDeleteSchema(ORMBaseSchema):
    deleted_at: Optional[datetime] = None


# =============================================================================
# Legacy: 기존 문서 공통 스키마
# =============================================================================

# TODO:
# 기존 문서 API와 그래프가 CommonDocumentSchema를 참조하고 있으므로
# Re:Call 파일 스키마 기반 구조로 마이그레이션할 때까지 유지한다.
#
# 삭제 조건:
# - CommonDocumentSchema 참조 제거
# - DocumentType 및 DEFAULT_DOCUMENT_TYPE 의존성 제거
# - 기존 문서 응답을 Re:Call 파일 스키마로 교체
# - 기존 API와 그래프 호환성 테스트 완료

CommonSource = Literal[
    "voice",
    "text",
    "pdf",
    "docx",
    "md",
    "image",
]

CommonStatus = Literal[
    "uploaded",
    "processing",
    "processed",
    "error",
]


# 기존 문서 처리 기능에서 사용하는 공통 문서 스키마
class CommonDocumentSchema(BaseModel):
    id: str
    title: str
    type: DocumentType = DEFAULT_DOCUMENT_TYPE
    source: CommonSource

    content: Optional[str] = None
    summary: Optional[str] = None
    language: str = "ko"

    created_at: str
    tags: list[str] = Field(default_factory=list)
    status: CommonStatus = "uploaded"

    notion_url: Optional[str] = None
    chroma_id: Optional[str] = None
    error: Optional[str] = None

    user_edited: bool = False
    chunks: list[dict[str, Any]] = Field(default_factory=list)