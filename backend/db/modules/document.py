"""일반 문서 / 이미지 OCR 분석 결과"""

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Numeric, String, Text
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
