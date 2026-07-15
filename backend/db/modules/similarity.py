"""그래프뷰용 문서 간 유사도 — 내 파트"""

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, uuid_pk


class FileSimilarity(Base):
    """
    서비스 계층에서 작은 UUID를 source_file_id, 큰 UUID를 target_file_id로
    정규화해서 중복 방향 저장을 막는다.
    MVP 그래프 대상: file_kind=document, analysis_status=completed, is_latest=true
    """

    __tablename__ = "file_similarities"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    target_file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    similarity_score = Column(Numeric(5, 4), nullable=False)
    embedding_model = Column(String(100), nullable=True)
    calculated_at = created_at_col()

    __table_args__ = (
        CheckConstraint("source_file_id != target_file_id", name="chk_file_similarities_distinct"),
        UniqueConstraint("source_file_id", "target_file_id", name="uq_file_similarities_pair"),
        Index("idx_file_similarities_workspace", "workspace_id", "similarity_score"),
    )
