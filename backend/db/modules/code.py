"""코드/설정 파일 분석 — 내 파트

CodeAnalysis: 파일 단위 분석 결과
CodeSymbol:   클래스/함수/메서드/API/상수 등 구조
CodeFact:     구조화된 사실 (모순 감지에서 가장 중요)
"""

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, Numeric,
    String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.db.base import Base
from backend.db.mixins import created_at_col, updated_at_col, uuid_pk


class CodeAnalysis(Base):
    __tablename__ = "code_analyses"

    id = uuid_pk()
    file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False, unique=True)
    language = Column(String(30), nullable=True)
    parser_name = Column(String(100), nullable=True)
    file_role = Column(String(30), nullable=False, server_default="unknown")
    summary = Column(Text, nullable=True)
    symbol_count = Column(Integer, nullable=False, server_default="0")
    fact_count = Column(Integer, nullable=False, server_default="0")
    processing_duration_ms = Column(BigInteger, nullable=True)
    analysis_status = Column(String(20), nullable=False, server_default="pending")
    processing_error = Column(Text, nullable=True)
    created_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        CheckConstraint(
            "file_role IN ('production','test','example','mock','generated','legacy','unknown')",
            name="chk_code_analyses_file_role",
        ),
    )


class CodeSymbol(Base):
    __tablename__ = "code_symbols"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    parent_symbol_id = Column(UUID(as_uuid=True), ForeignKey("code_symbols.id"), nullable=True)
    symbol_type = Column(String(30), nullable=False)
    symbol_name = Column(String(255), nullable=False)
    qualified_name = Column(Text, nullable=True)
    signature = Column(Text, nullable=True)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    code_text = Column(Text, nullable=False)
    docstring = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "symbol_type IN ('module','class','function','method','api_endpoint',"
            "'config','constant','variable')",
            name="chk_code_symbols_type",
        ),
        Index("idx_code_symbols_file", "file_id", "symbol_type", "symbol_name"),
    )


class CodeFact(Base):
    __tablename__ = "code_facts"

    id = uuid_pk()
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey("workspace_files.id"), nullable=False)
    symbol_id = Column(UUID(as_uuid=True), ForeignKey("code_symbols.id"), nullable=True)
    fact_type = Column(String(50), nullable=False)
    fact_key = Column(String(255), nullable=False)
    fact_value = Column(JSONB, nullable=False)
    normalized_value = Column(Text, nullable=True)
    environment = Column(String(30), nullable=False, server_default="unknown")
    confidence_score = Column(Numeric(5, 4), nullable=True)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    evidence_text = Column(Text, nullable=False)
    created_at = created_at_col()
    updated_at = updated_at_col()

    __table_args__ = (
        CheckConstraint(
            "environment IN ('production','development','test','unknown')",
            name="chk_code_facts_environment",
        ),
        Index("idx_code_facts_lookup", "workspace_id", "fact_type", "fact_key", "environment"),
    )
