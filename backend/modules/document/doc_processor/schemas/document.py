from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from doc_processor.schemas.metadata import DocumentMetadata, PageResultSchema

# 팀 공통 status 값
DocumentStatus = Literal["uploaded", "processing", "processed", "error"]


class DocumentSchema(BaseModel):
    """팀 공통 JSON 스키마 — 문서 처리 모듈 최종 출력."""

    # ── 팀 공통 키 ──────────────────────────────────────
    id: str
    title: str
    type: Literal["document"] = "document"
    source: Literal["pdf"] = "pdf"          # 출처 유형 고정값
    content: str                             # plain text 전체 (PyMuPDF + OCR + 표)
    content_markdown: str = ""              # Markdown 전체
    summary: str = ""                       # 향후 LLM 요약 결과
    language: str = "ko"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tags: list[str] = Field(default_factory=list)
    status: DocumentStatus = "processed"
    notion_url: str | None = None
    chroma_id: str | None = None
    error: str | None = None
    user_edited: bool = False

    # ── 문서 처리 전용 키 ────────────────────────────────
    tables: list[dict] = Field(default_factory=list)   # VL 추출 표 [{page, markdown}]
    charts: list[dict] = Field(default_factory=list)   # VL 추출 차트 [{page, raw_text, data}]
    chunks: list[dict] = Field(default_factory=list)   # 전체 텍스트 청크 (caption 제외, title/body만)
    page_results: list[PageResultSchema] = Field(default_factory=list)
    metadata: DocumentMetadata
