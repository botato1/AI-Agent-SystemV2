# backend/schemas/file_similarity_schema.py

"""
문서 유사도 그래프(file_similarities) 관련 Pydantic 스키마를 정의한다.
그래프 뷰에서 사용하는 파일 간 유사도 계산 결과를 저장한다.

MVP 그래프 대상:
- workspace_files.file_kind = "document"
- workspace_files.analysis_status = "completed"
- workspace_files.is_latest = True

중복 방향 저장 방지 규칙:
- source_file_id와 target_file_id의 UUID 정수값을 비교한다.
- 더 작은 UUID를 source_file_id로 저장한다.
- 더 큰 UUID를 target_file_id로 저장한다.
- 해당 정규화는 서비스 계층에서 처리한다.

서비스 계층에서 다음 관계를 검증해야 한다.
- 두 파일이 모두 file_similarities.workspace_id에 속하는지 확인
- 두 파일이 삭제되지 않았는지 확인
- 두 파일이 MVP 그래프 대상 조건을 만족하는지 확인

TODO:
- 유사도 그래프 조회 API의 요청·응답 스키마는
  관련 라우터 구현 시 별도로 정의
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field, model_validator

from backend.schemas.common_schema import ORMBaseSchema


# =============================================================================
# Re:Call: file_similarities
# =============================================================================

class FileSimilaritySchema(ORMBaseSchema):
    """
    그래프 뷰에서 사용하는 파일 간 유사도 하나를 표현한다.

    file_similarities 테이블에는 created_at과 updated_at이 없으므로
    calculated_at만 직접 선언한다.

    DB 제약조건:

        source_file_id != target_file_id
        UNIQUE(source_file_id, target_file_id)
    """

    id: UUID
    workspace_id: UUID

    source_file_id: UUID
    target_file_id: UUID

    similarity_score: Decimal = Field(
        ...,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )
    embedding_model: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    calculated_at: datetime

    @model_validator(mode="after")
    def _validate_distinct_files(self) -> "FileSimilaritySchema":
        if self.source_file_id == self.target_file_id:
            raise ValueError(
                "source_file_id와 target_file_id는 달라야 합니다."
            )

        return self