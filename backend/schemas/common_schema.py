# 공통 문서/STT 타입 정의 (v2 기준)
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field

from backend.schemas.type_schema import DocumentType, DEFAULT_DOCUMENT_TYPE

# common_schema는 문서 + STT 공통 구조이므로 voice 포함 가능
CommonSource = Literal["voice", "text", "pdf", "docx", "md", "image"]

CommonStatus = Literal["uploaded", "processing", "processed", "error"]


class CommonDocumentSchema(BaseModel):
    id: str
    title: str

    # v2 법률 도메인 기준 자료 유형
    type: DocumentType = DEFAULT_DOCUMENT_TYPE

    # 입력 형식
    source: CommonSource

    # 원문 텍스트 또는 STT 전체 텍스트
    content: Optional[str] = None

    # AI 요약본
    summary: Optional[str] = None

    language: str = "ko"
    created_at: str

    tags: list[str] = Field(default_factory=list)
    status: CommonStatus = "uploaded"

    # v1 호환용 / 선택 필드
    notion_url: Optional[str] = None
    chroma_id: Optional[str] = None
    error: Optional[str] = None

    # 사용자가 STT/문서 처리 결과를 직접 수정했는지 여부
    user_edited: bool = False

    # v2에서는 단순 문자열보다 chunk dict 구조가 더 적합함
    chunks: list[dict[str, Any]] = Field(default_factory=list)