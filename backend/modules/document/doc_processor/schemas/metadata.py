from __future__ import annotations

from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """청크 단위 메타데이터."""

    confidence_score: float = Field(ge=0.0, le=1.0)
    engines: list[str]
    fallback_used: bool = False

    # text 청크 전용
    style: str | None = None
    font: str | None = None
    size: float | None = None

    # table 청크 전용
    rows: int | None = None
    cols: int | None = None

    # image / chart 청크 전용
    voting_confidence: float | None = None
    source_engines: list[str] | None = None
    ocr_quality_score: float | None = None   # OCR 품질 점수 (관측용)

    # Gemini Fallback 추가 시 채워짐
    gemini_corrected: bool = False
    gemini_model: str | None = None


class PageResultSchema(BaseModel):
    """page_results 배열의 단일 페이지 — 디버깅용."""

    page_number: int
    text_blocks: list[dict] = Field(default_factory=list)
    tables: list[dict] = Field(default_factory=list)
    images: list[dict] = Field(default_factory=list)
    charts: list[dict] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    fallback_used: bool = False


class DocumentMetadata(BaseModel):
    """문서 단위 메타데이터."""

    confidence_score: float = Field(ge=0.0, le=1.0)
    engines: list[str]
    fallback_used: bool = False
    page_count: int = Field(ge=1)
    file_path: str = ""        # source 키에서 분리한 실제 경로
    pdf_type: str = "digital"  # "digital" | "scanned" | "mixed"
    fallback_candidate: bool = False  # True면 Gemini 보정 권장 (낮은 confidence)

    # OCR 실행 통계
    ocr_attempt_count: int = 0       # FigureClassifier 평가 대상 총 이미지 수
    ocr_skip_count: int = 0          # 타입 기반 SKIP 수
    ocr_success_count: int = 0       # OCR 실행 후 텍스트 추출 성공 수
    ocr_empty_count: int = 0         # OCR 실행했으나 텍스트 없음 (빈 이미지)
    ocr_filtered_count: int = 0      # voter 품질 필터로 제거된 수
    ocr_useful_count: int = 0         # quality_score >= threshold (관측용, 자동 필터 아님)
    ocr_garbage_count: int = 0        # quality_score <  threshold (관측용, 자동 필터 아님)
    ocr_avg_quality_score: float = 0.0  # OCR 품질 점수 평균 (관측용)
    ocr_skip_ratio: float = 0.0       # skip_count / attempt_count
    ocr_success_ratio: float = 0.0    # success_count / attempt_count
    ocr_useful_ratio: float = 0.0     # useful_count / success_count
    ocr_surya_ratio: float = 0.0      # paddle_surya_count / run_count
    ocr_paddle_only_count: int = 0         # Surya 없이 Paddle만 실행한 수 (이유 무관)
    ocr_paddle_surya_count: int = 0        # Paddle+Surya 양쪽 실행한 수
    ocr_chart_paddle_only_count: int = 0   # chart/diagram fig_type으로 인한 Paddle 단독 수
    ocr_table_tsr_count: int = 0           # table_image TSR+CellOCR 경로 실행 수

    # 처리 시간
    processing_time_sec: float = 0.0  # 문서 전체 처리 시간 (초)
    pages_per_second: float = 0.0     # page_count / processing_time_sec
