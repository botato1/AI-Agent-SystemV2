"""ChromaDB 연결용 콘텐츠 청크 — 내 파트

일반 문서 + 코드/설정 + 이미지 OCR + 회의(세그먼트/요약) 청크를 통합 관리.
실제 임베딩 벡터는 ChromaDB에 저장되고 chroma_id로 연결된다.
"""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class ContentChunk(Base):
    __tablename__ = "content_chunks"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    symbol_id = Column(UUID(as_uuid=True), ForeignKey("code_symbols.id"), nullable=True)
    chunk_type = Column(String(30), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    section_title = Column(String(255), nullable=True)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    chroma_id = Column(String(255), nullable=False, unique=True)
    embedding_model = Column(String(100), nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        CheckConstraint(
            "chunk_type IN ('document_text','code_symbol','config_text','image_ocr',"
            "'meeting_segment','meeting_summary')",
            name="chk_content_chunks_type",
        ),
        UniqueConstraint("file_id", "chunk_type", "chunk_index", name="uq_content_chunks_file_chunk"),
        Index("idx_content_chunks_file", "file_id", "chunk_type", "chunk_index"),
        Index("idx_content_chunks_workspace", "workspace_id", "file_id"),
    )
