# backend/schemas/content_chunk_schema.py

"""
콘텐츠 청크(content_chunks) 관련 Pydantic 스키마를 정의한다.

문서, 코드, 설정, 이미지 OCR, 회의 발언, 회의 요약의
검색 청크를 하나의 테이블에서 통합 관리한다.

카테고리 범위 설계:
- content_chunks.category_id는 원본 workspace_files.category_id를
  서비스 계층에서 복사하여 저장한다.
- 회의 발언 및 회의 요약 청크의 file_id는 회의 원본 음성 파일을 가리킨다.
- 원본 파일과 청크의 workspace_id 및 category_id가 일치하는지
  서비스 계층에서 검증한다.
- ChromaDB metadata에도 workspace_id와 category_id를 저장하여
  검색 범위 필터로 사용한다.

chunk_type별 FK 일관성:
- meeting_segment:
  meeting_segment_id 필수, meeting_summary_id는 NULL
- meeting_summary:
  meeting_summary_id 필수, meeting_segment_id는 NULL
- 그 외:
  meeting_segment_id와 meeting_summary_id 모두 NULL

위 규칙은 DB CHECK 제약과 Pydantic model_validator에서 모두 검증한다.

서비스 계층 및 DB에서 처리할 제약:
- UNIQUE(file_id, chunk_type, chunk_index)
- chroma_id UNIQUE
- content_chunks.workspace_id = workspace_files.workspace_id
- content_chunks.category_id = workspace_files.category_id

TODO:
- ChromaDB에 전달할 metadata 구성은 서비스 계층에서 처리
- 콘텐츠 청크 조회 API의 요청·응답 스키마는 관련 라우터 구현 시 별도 정의
"""

from typing import Any, Optional
from uuid import UUID

from pydantic import Field, model_validator

from backend.schemas.common_schema import TimestampSchema
from backend.schemas.type_schema import ContentChunkType


# =============================================================================
# Re:Call: content_chunks
# =============================================================================

class ContentChunkSchema(TimestampSchema):
    """
    문서, 코드, 설정, 이미지 OCR, 회의 발언, 회의 요약의
    검색 청크 하나를 표현한다.

    PostgreSQL의 청크 데이터와 ChromaDB의 임베딩 벡터는
    chroma_id를 기준으로 연결한다.
    """

    id: UUID
    workspace_id: UUID
    category_id: UUID

    file_id: UUID
    symbol_id: Optional[UUID] = None
    meeting_segment_id: Optional[UUID] = None
    meeting_summary_id: Optional[UUID] = None

    chunk_type: ContentChunkType
    chunk_index: int = Field(
        ...,
        ge=0,
    )
    chunk_text: str = Field(
        ...,
        min_length=1,
    )

    page_number: Optional[int] = Field(
        default=None,
        ge=1,
    )
    section_title: Optional[str] = Field(
        default=None,
        max_length=255,
    )
    start_line: Optional[int] = Field(
        default=None,
        ge=1,
    )
    end_line: Optional[int] = Field(
        default=None,
        ge=1,
    )

    rag_enabled: bool

    chroma_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    embedding_model: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    metadata_json: Optional[dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_chunk_consistency(self) -> "ContentChunkSchema":
        if self.chunk_type == "meeting_segment":
            if self.meeting_segment_id is None:
                raise ValueError(
                    "chunk_type이 meeting_segment이면 "
                    "meeting_segment_id가 필수입니다."
                )

            if self.meeting_summary_id is not None:
                raise ValueError(
                    "chunk_type이 meeting_segment이면 "
                    "meeting_summary_id는 NULL이어야 합니다."
                )

        elif self.chunk_type == "meeting_summary":
            if self.meeting_summary_id is None:
                raise ValueError(
                    "chunk_type이 meeting_summary이면 "
                    "meeting_summary_id가 필수입니다."
                )

            if self.meeting_segment_id is not None:
                raise ValueError(
                    "chunk_type이 meeting_summary이면 "
                    "meeting_segment_id는 NULL이어야 합니다."
                )

        elif (
            self.meeting_segment_id is not None
            or self.meeting_summary_id is not None
        ):
            raise ValueError(
                f"chunk_type이 {self.chunk_type}이면 "
                "meeting_segment_id와 meeting_summary_id는 "
                "모두 NULL이어야 합니다."
            )

        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError(
                "end_line은 start_line보다 크거나 같아야 합니다."
            )

        return self