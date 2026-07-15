from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class LayoutBlock:
    """Docling 레이아웃 분석 결과 — 단일 블록."""

    type: str          # "heading" | "paragraph" | "table" | "figure" | "caption"
                       # "header" | "footer" | "list" | "code" | "formula"
    page: int          # 1-based
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 (pt, top-left origin)
    content: str = ""  # 텍스트 블록의 내용 (figure는 빈 문자열)

    # figure 전용 필드
    figure_type: str = "unknown"   # "photo" | "chart" | "diagram" | "logo" | "unknown"
    has_caption: bool = False      # 주변에 caption 블록이 존재하는지
    ocr_skip: bool = False         # True = OCR 불필요 (로고/아이콘/배너)


@dataclass
class TextBlock:
    text: str
    bbox: list[float]
    font: str = ""
    size: float = 0.0
    style: str = "body"  # "title" | "heading" | "body" | "caption"


@dataclass
class TableBlock:
    data: list[list[Any]]
    markdown: str
    bbox: list[float]


@dataclass
class ImageBlock:
    bbox: list[float]
    ocr_text: str
    voting_confidence: float
    source_engines: list[str]
    paddle_lines: list[str] = field(default_factory=list)
    quality_score: float = -1.0   # OCR 품질 점수 (0.0~1.0, -1.0=미계산)
    debug: dict | None = None     # debug_ocr=True 일 때만 채워짐


@dataclass
class ChartBlock:
    bbox: list[float]
    description: str = ""
    extracted_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageContent:
    text: list[TextBlock] = field(default_factory=list)
    tables: list[TableBlock] = field(default_factory=list)
    images: list[ImageBlock] = field(default_factory=list)
    charts: list[ChartBlock] = field(default_factory=list)


@dataclass
class ConfidenceScore:
    text: float = 1.0
    table: float = 1.0
    image: float = 1.0
    chart: float = 1.0
    overall: float = 1.0

    def to_dict(self) -> dict[str, float]:
        return {
            "text": self.text,
            "table": self.table,
            "image": self.image,
            "chart": self.chart,
            "overall": self.overall,
        }

    def any_below(self, threshold: float) -> bool:
        # overall 제외하고 개별 항목만 체크
        return any(
            v < threshold
            for k, v in self.to_dict().items()
            if k != "overall"
        )


@dataclass
class PageResult:
    page: int
    content: PageContent
    confidence: ConfidenceScore = field(default_factory=ConfidenceScore)
    fallback_used: bool = False
    engine: str = "pymupdf+pdfplumber+paddle"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "content": {
                "text": [
                    {"text": b.text, "bbox": b.bbox, "font": b.font, "size": b.size, "style": b.style}
                    for b in self.content.text
                ],
                "tables": [
                    {"data": b.data, "markdown": b.markdown, "bbox": b.bbox}
                    for b in self.content.tables
                ],
                "images": [
                    {
                        "bbox": b.bbox,
                        "ocr_text": b.ocr_text,
                        "voting_confidence": b.voting_confidence,
                        "source_engines": b.source_engines,
                    }
                    for b in self.content.images
                ],
                "charts": [
                    {"bbox": b.bbox, "description": b.description, "extracted_data": b.extracted_data}
                    for b in self.content.charts
                ],
            },
            "confidence": self.confidence.to_dict(),
            "fallback_used": self.fallback_used,
            "engine": self.engine,
            "created_at": self.created_at,
        }


@dataclass
class OcrStats:
    """문서 단위 OCR 실행 통계."""

    # ── 시도/스킵 ────────────────────────────────────────────────────────────
    attempt_count: int = 0   # OCR 시도 횟수 (FigureClassifier 평가 + full_page 포함)
    skip_count: int = 0      # 타입 기반 SKIP 횟수

    # ── 실행 결과 분류 ────────────────────────────────────────────────────────
    success_count: int = 0   # OCR 실행 후 텍스트 추출 성공 횟수
    empty_count: int = 0     # OCR 실행했으나 텍스트 없음 (빈 이미지)
    filtered_count: int = 0  # voter 품질 필터에 걸린 횟수

    # ── 품질 분류 (관측용, 자동 필터 아님) ──────────────────────────────────
    useful_count: int = 0    # quality_score >= QUALITY_USEFUL_THRESHOLD
    garbage_count: int = 0   # quality_score <  QUALITY_USEFUL_THRESHOLD

    # ── 엔진 경로 통계 ────────────────────────────────────────────────────────
    paddle_only_count: int = 0         # Paddle 실행 횟수
    chart_paddle_only_count: int = 0   # chart/diagram fig_type Paddle 단독 횟수
    table_tsr_count: int = 0           # table_image TSR+CellOCR 경로 실행 횟수

    # ── 처리 시간 ─────────────────────────────────────────────────────────────
    processing_time_sec: float = 0.0   # 문서 전체 처리 시간 (초)

    # ── quality_score 누적 (avg 계산용, __init__ 파라미터 아님) ──────────────
    _quality_score_sum:   float = field(default=0.0, init=False, repr=False)
    _quality_score_count: int   = field(default=0,   init=False, repr=False)

    # ── 엔진별 문자 수 누적 (avg_*_length 계산용) ─────────────────────────────
    _paddle_char_sum: int = field(default=0, init=False, repr=False)
    _voted_char_sum:  int = field(default=0, init=False, repr=False)
    _engine_char_n:   int = field(default=0, init=False, repr=False)

    # ── 누적 메서드 ───────────────────────────────────────────────────────────

    def accumulate_quality_score(self, score: float) -> None:
        """quality_score를 누적합니다 (avg_quality_score 계산용)."""
        if score >= 0.0:
            self._quality_score_sum   += score
            self._quality_score_count += 1

    def accumulate_char_counts(
        self,
        paddle_chars: int,
        voted_chars: int,
    ) -> None:
        """엔진별 문자 수를 누적합니다 (avg_*_length 계산용)."""
        self._paddle_char_sum += paddle_chars
        self._voted_char_sum  += voted_chars
        self._engine_char_n   += 1

    # ── 파생 통계 (property) ─────────────────────────────────────────────────

    @property
    def run_count(self) -> int:
        """실제 OCR 엔진이 실행된 횟수 (attempt - skip)."""
        return self.attempt_count - self.skip_count

    @property
    def skip_ratio(self) -> float:
        """스킵 비율 (0.0~1.0)."""
        if self.attempt_count == 0:
            return 0.0
        return round(self.skip_count / self.attempt_count, 3)

    @property
    def success_ratio(self) -> float:
        """성공 비율 = success / attempt (0.0~1.0)."""
        if self.attempt_count == 0:
            return 0.0
        return round(self.success_count / self.attempt_count, 3)

    @property
    def useful_ratio(self) -> float:
        """유용 비율 = useful / success (0.0~1.0)."""
        if self.success_count == 0:
            return 0.0
        return round(self.useful_count / self.success_count, 3)

    @property
    def avg_quality_score(self) -> float:
        """누적된 quality_score의 평균값 (0.0~1.0). 집계 없으면 0.0."""
        if self._quality_score_count == 0:
            return 0.0
        return round(self._quality_score_sum / self._quality_score_count, 3)

    @property
    def avg_paddle_length(self) -> float:
        """Paddle 결과의 평균 문자 수."""
        if self._engine_char_n == 0:
            return 0.0
        return round(self._paddle_char_sum / self._engine_char_n, 1)

    @property
    def avg_voted_length(self) -> float:
        """Voting 결과의 평균 문자 수."""
        if self._engine_char_n == 0:
            return 0.0
        return round(self._voted_char_sum / self._engine_char_n, 1)

    @property
    def pages_per_second(self) -> float:
        """페이지 처리 속도. processing_time_sec가 0이면 0.0."""
        # page_count는 OcrStats에 없으므로 호출 측에서 넘겨야 함 → 별도 메서드로 제공
        return 0.0  # 호환성 유지용 stub; print_summary에 page_count 전달로 계산

    # ── 관계식 검증 ───────────────────────────────────────────────────────────

    def validate_counts(self) -> bool:
        """집계 관계식이 성립하는지 검증하고, 어긋나면 WARNING을 출력합니다.

        검증식:
          1) run_count == paddle_only_count + table_tsr_count
             (실행한 엔진 수의 합이 run_count와 일치)
          2) run_count == success_count + empty_count + filtered_count
             (실행 결과의 분류 합이 run_count와 일치)
          3) success_count == useful_count + garbage_count
             (성공 결과의 품질 분류 합이 success_count와 일치)

        Returns:
            True: 모든 관계식 성립 / False: 하나 이상 불일치
        """
        ok = True
        run = self.run_count
        engine_sum = self.paddle_only_count + self.table_tsr_count
        result_sum = self.success_count + self.empty_count + self.filtered_count
        quality_sum = self.useful_count + self.garbage_count

        if run != engine_sum:
            print(
                f"[OcrStats WARNING] 관계식 1 불일치: "
                f"run_count({run}) != paddle_only({self.paddle_only_count})"
                f" + table_tsr({self.table_tsr_count}) = {engine_sum}"
            )
            ok = False
        if run != result_sum:
            print(
                f"[OcrStats WARNING] 관계식 2 불일치: "
                f"run_count({run}) != success({self.success_count})"
                f" + empty({self.empty_count}) + filtered({self.filtered_count}) = {result_sum}"
            )
            ok = False
        if self.success_count != quality_sum:
            print(
                f"[OcrStats WARNING] 관계식 3 불일치: "
                f"success_count({self.success_count}) != "
                f"useful({self.useful_count}) + garbage({self.garbage_count}) = {quality_sum}"
            )
            ok = False

        return ok

    # ── 요약 출력 ─────────────────────────────────────────────────────────────

    def print_summary(self, page_count: int = 0) -> None:
        """OCR 성능 통계를 블록 형식으로 출력합니다.

        Args:
            page_count: 문서 총 페이지 수 (처리 속도 계산용).
        """
        self.validate_counts()

        run  = self.run_count
        pps  = (page_count / self.processing_time_sec
                if self.processing_time_sec > 0 and page_count > 0 else 0.0)
        aps  = (run / self.processing_time_sec
                if self.processing_time_sec > 0 else 0.0)

        W = 50  # 구분선 너비
        print("=" * W)
        print("OCR SUMMARY")
        print("=" * W)
        print()
        print(f"  {'Attempt Count':<22}: {self.attempt_count}")
        print(f"  {'Skip Count':<22}: {self.skip_count}")
        print()
        print(f"  {'Run Count':<22}: {run}")
        print()
        print(f"  {'Success Count':<22}: {self.success_count}")
        print(f"  {'Empty Count':<22}: {self.empty_count}")
        print(f"  {'Filtered Count':<22}: {self.filtered_count}")
        print(f"  {'Garbage Count':<22}: {self.garbage_count}")
        print(f"  {'Useful Count':<22}: {self.useful_count}")
        print()
        print(f"  {'Paddle Runs':<22}: {self.paddle_only_count}")
        print(f"  {'  (chart/diagram)':<22}: {self.chart_paddle_only_count}")
        print(f"  {'Table TSR Runs':<22}: {self.table_tsr_count}")
        print()
        print(f"  {'Avg Paddle Length':<22}: {self.avg_paddle_length:.1f} chars")
        print(f"  {'Avg Voted Length':<22}: {self.avg_voted_length:.1f} chars")
        print()
        print(f"  {'Skip Ratio':<22}: {self.skip_ratio*100:.1f}%")
        print(f"  {'Success Ratio':<22}: {self.success_ratio*100:.1f}%")
        print(f"  {'Useful Ratio':<22}: {self.useful_ratio*100:.1f}%")
        print()
        print(f"  {'Avg Quality Score':<22}: {self.avg_quality_score:.3f}")
        print()
        if page_count > 0 or self.processing_time_sec > 0:
            print(f"  {'Total Pages':<22}: {page_count}")
            print(f"  {'Total Time':<22}: {self.processing_time_sec:.1f} sec")
            if pps > 0:
                print(f"  {'Pages / Second':<22}: {pps:.2f}")
            if aps > 0:
                print(f"  {'OCR Attempts / Sec':<22}: {aps:.2f}")
            print()
        print("=" * W)


@dataclass
class DocumentResult:
    source: str
    pdf_type: str  # "digital" | "scanned" | "mixed"
    pages: list[PageResult] = field(default_factory=list)
    ocr_stats: OcrStats = field(default_factory=OcrStats)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "pdf_type": self.pdf_type,
            "pages": [p.to_dict() for p in self.pages],
        }
