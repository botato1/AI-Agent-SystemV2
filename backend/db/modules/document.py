"""일반 문서 / 이미지 OCR 분석 결과"""

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, ForeignKey, Index,
    Integer, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class DocumentAnalysis(Base):
    """workspace_files.file_kind가 document 또는 image인 파일의 분석 결과."""

    __tablename__ = "document_analyses"

    id = uuid_pk()
    file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False, unique=True)
    extracted_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    ocr_avg_confidence = Column(Numeric(5, 4), nullable=True)
    ocr_required_pages = Column(Integer, nullable=False, server_default="0")
    ocr_success_pages = Column(Integer, nullable=False, server_default="0")
    table_count = Column(Integer, nullable=False, server_default="0")
    graph_count = Column(Integer, nullable=False, server_default="0")
    diagram_count = Column(Integer, nullable=False, server_default="0")
    processing_duration_ms = Column(BigInteger, nullable=True)
    analysis_status = Column(String(20), nullable=False, server_default="pending")
    processing_error = Column(Text, nullable=True)
    model_name = Column(String(100), nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

class DocumentFigure(Base):
    """문서 분석 시 감지된 표/차트/다이어그램의 크롭 이미지 참조."""

    __tablename__ = "document_figures"

    id = uuid_pk()
    file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    figure_type = Column(String(20), nullable=False)
    image_url = Column(Text, nullable=False)
    display_order = Column(Integer, nullable=False, server_default="0")
    created_at = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "figure_type IN ('table','chart','image','diagram')",
            name="chk_document_figures_type",
        ),
        Index("idx_document_figures_file", "file_id", "page_number"),
    )