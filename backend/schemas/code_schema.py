# backend/schemas/code_schema.py

"""
코드 및 설정 파일 분석 관련 Pydantic 스키마를 정의한다.

workspace_files.file_kind가 code 또는 config인 파일의
AST 및 구문 분석 결과를 다룬다.

카테고리 범위 설계:
- code_analyses와 code_symbols는 file_id를 통해
  workspace_files.category_id를 확인할 수 있으므로
  category_id를 별도로 저장하지 않는다.
- code_facts는 카테고리별 모순 감지와 구조화된 사실 검색에
  직접 사용되므로 category_id를 반정규화하여 저장한다.
- code_facts.category_id는 분석 대상 workspace_files.category_id를
  서비스 계층에서 복사하여 저장한다.

모순 감지 우선순위:
- code_analyses.file_role이 production인 파일을 우선 사용한다.
- test, example, mock, generated, legacy 파일은 낮은 우선순위로
  처리하거나 기본 검색 대상에서 제외할 수 있다.

TODO:
- 코드 분석 결과 조회 API의 요청·응답 스키마는
  관련 라우터 구현 시 별도로 정의
- code_facts 생성 시 category_id가 원본 파일의 category_id와
  일치하는지 서비스 계층에서 검증
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from backend.schemas.common_schema import (
    ORMBaseSchema,
    TimestampSchema,
)
from backend.schemas.type_schema import (
    CodeFactType,
    CodeFileRole,
    CodeSymbolType,
    FactEnvironment,
    FileAnalysisStatus,
)


# =============================================================================
# Re:Call: code_analyses
# =============================================================================

class CodeAnalysisSchema(TimestampSchema):
    """
    코드 또는 설정 파일의 파일 단위 분석 결과를 표현한다.

    file_id는 workspace_files.id를 참조하며,
    파일당 분석 결과 하나만 존재하도록 DB에서 UNIQUE 제약을 적용한다.
    """

    id: UUID
    file_id: UUID

    language: Optional[str] = Field(
        default=None,
        max_length=30,
    )
    parser_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    file_role: CodeFileRole

    summary: Optional[str] = None

    symbol_count: int = Field(
        ...,
        ge=0,
    )
    fact_count: int = Field(
        ...,
        ge=0,
    )

    processing_duration_ms: Optional[int] = Field(
        default=None,
        ge=0,
    )
    analysis_status: FileAnalysisStatus
    processing_error: Optional[str] = None


# =============================================================================
# Re:Call: code_symbols
# =============================================================================

class CodeSymbolSchema(ORMBaseSchema):
    """
    클래스, 함수, 메서드, API 엔드포인트, 상수 등
    코드 구조 하나를 표현한다.

    code_symbols 테이블에는 updated_at 컬럼이 없으므로
    created_at만 포함한다.

    서비스 계층에서 다음 규칙을 검증한다.

        end_line >= start_line

    parent_symbol_id가 존재하면 같은 file_id에 속한 심볼인지 확인한다.
    """

    id: UUID
    workspace_id: UUID
    file_id: UUID
    parent_symbol_id: Optional[UUID] = None

    symbol_type: CodeSymbolType
    symbol_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    qualified_name: Optional[str] = None
    signature: Optional[str] = None

    start_line: int = Field(
        ...,
        ge=1,
    )
    end_line: int = Field(
        ...,
        ge=1,
    )

    code_text: str = Field(
        ...,
        min_length=1,
    )
    docstring: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None

    created_at: datetime


# =============================================================================
# Re:Call: code_facts
# =============================================================================

class CodeFactSchema(TimestampSchema):
    """
    코드에서 추출한 구조화된 사실 하나를 표현한다.

    코드 기준 모순 감지에서 포트, 데이터베이스 종류,
    API 엔드포인트, 환경변수 등의 정확한 값을 비교할 때 사용한다.

    category_id는 원본 workspace_files.category_id를 복사하여 저장한다.

    예시: 서버 포트

        fact_type = "server_port"
        fact_key = "fastapi"
        fact_value = {"port": 8000}
        normalized_value = "8000"

    예시: API 엔드포인트

        fact_type = "api_endpoint"
        fact_key = "create_room"
        fact_value = {
            "method": "POST",
            "path": "/api/workspaces/{workspace_id}/rooms"
        }
        normalized_value =
            "POST:/api/workspaces/{workspace_id}/rooms"
    """

    id: UUID
    workspace_id: UUID
    category_id: UUID
    file_id: UUID
    symbol_id: Optional[UUID] = None

    fact_type: CodeFactType
    fact_key: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    fact_value: dict[str, Any]
    normalized_value: Optional[str] = None

    environment: FactEnvironment

    confidence_score: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )

    start_line: Optional[int] = Field(
        default=None,
        ge=1,
    )
    end_line: Optional[int] = Field(
        default=None,
        ge=1,
    )

    evidence_text: str = Field(
        ...,
        min_length=1,
    )