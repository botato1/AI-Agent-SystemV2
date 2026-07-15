"""Docling 레이아웃 파서.

역할:
    PDF를 Docling으로 분석하여 Heading / Paragraph / Table / Figure / Caption
    블록 목록을 반환한다.  OCR은 수행하지 않으며 레이아웃 정보만 제공한다.

폴백:
    Docling이 설치되지 않았거나 분석 실패 시 빈 dict를 반환한다.
    호출 측은 반환값이 비어 있으면 기존 PyMuPDF 기반 흐름을 그대로 사용한다.

설치된 버전 기준 API:
    - PictureItem  (FigureItem 아님)
    - DocItemLabel.PICTURE, CHART  (FIGURE 없음)
    - Prov.bbox → list[float] [l, t, r, b]
    - Prov.page → int  (page_no 아님)
    - DoclingDocument.pages → dict[int, PageItem]
    - PageItem.size → Size(width, height)
    - CoordOrigin → docling_core.types.doc.base
"""
from __future__ import annotations

import logging
from pathlib import Path

from doc_processor.core.models import LayoutBlock

logger = logging.getLogger(__name__)

# ── Docling 선택적 임포트 ──────────────────────────────────────────────────────

_DOCLING_AVAILABLE = False

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.document import (
        DocItemLabel,
        DoclingDocument,
        PictureItem,
        TableItem,
        TextItem,
        SectionHeaderItem,
        ListItem,
    )
    from docling_core.types.doc.base import CoordOrigin
    _DOCLING_AVAILABLE = True
except ImportError:
    pass

# ── 레이블 → 내부 type 문자열 매핑 ────────────────────────────────────────────

if _DOCLING_AVAILABLE:
    _LABEL_MAP: dict = {
        DocItemLabel.SECTION_HEADER: "heading",
        DocItemLabel.TEXT:           "paragraph",
        DocItemLabel.PARAGRAPH:      "paragraph",
        DocItemLabel.LIST_ITEM:      "list",
        DocItemLabel.TABLE:          "table",
        DocItemLabel.PICTURE:        "figure",
        DocItemLabel.CHART:          "figure",   # 차트도 figure로 취급 (ocr_skip=False)
        DocItemLabel.CAPTION:        "caption",
        DocItemLabel.PAGE_HEADER:    "header",
        DocItemLabel.PAGE_FOOTER:    "footer",
        DocItemLabel.CODE:           "code",
        DocItemLabel.FORMULA:        "formula",
    }
    # CHART는 별도로 figure_type="chart" 처리
    _CHART_LABELS: set = {DocItemLabel.CHART}

# ── Figure 유형 분류 (휴리스틱) ────────────────────────────────────────────────

_LOGO_MAX_AREA_RATIO  = 0.015   # 1.5% 이하 + 캡션 없음 → 로고
_CHART_MIN_AREA_RATIO = 0.04    # 4% 이상 → 컨텐츠 이미지
_HEADER_ZONE_RATIO    = 0.10    # 페이지 상단 10% 이내
_BANNER_WIDTH_RATIO   = 0.70    # 배너: 가로 ≥ 70%
_BANNER_HEIGHT_RATIO  = 0.05    # 배너: 세로 ≤ 5%


def _classify_figure(
    bbox: tuple[float, float, float, float],
    page_w: float,
    page_h: float,
    has_caption: bool,
    is_chart_label: bool = False,
) -> tuple[str, bool]:
    """Figure 블록을 분류하고 OCR 스킵 여부를 반환합니다.

    Returns:
        (figure_type, ocr_skip)
    """
    # 정규화: 좌표 역전 방지
    x0, y0, x1, y1 = (
        min(bbox[0], bbox[2]), min(bbox[1], bbox[3]),
        max(bbox[0], bbox[2]), max(bbox[1], bbox[3]),
    )
    w = x1 - x0
    h = y1 - y0
    area = w * h
    page_area = page_w * page_h

    if page_area <= 0:
        return "unknown", False

    area_ratio = area / page_area

    # Docling이 이미 차트로 분류한 경우 → OCR 수행
    if is_chart_label:
        return "chart", False

    # 1. 배너 패턴
    if w / page_w >= _BANNER_WIDTH_RATIO and h / page_h <= _BANNER_HEIGHT_RATIO:
        return "logo", True

    # 2. 페이지 상단의 작은 이미지 → 로고
    if (y0 / page_h) <= _HEADER_ZONE_RATIO and area_ratio <= _LOGO_MAX_AREA_RATIO:
        return "logo", True

    # 3. 아주 작고 캡션도 없음 → 아이콘/로고
    if area_ratio <= _LOGO_MAX_AREA_RATIO and not has_caption:
        return "logo", True

    # 4. 충분히 크고 캡션 있음 → 콘텐츠 이미지
    if area_ratio >= _CHART_MIN_AREA_RATIO and has_caption:
        return "chart", False

    # 5. 크지만 캡션 없음 → unknown, OCR 시도
    if area_ratio >= _CHART_MIN_AREA_RATIO:
        return "unknown", False

    return "unknown", False


# ── Docling 파서 클래스 ────────────────────────────────────────────────────────

_CHUNK_THRESHOLD = 150   # 이 페이지 수 초과 시 분할 처리
_CHUNK_SIZE      = 100   # 분할 단위 (페이지)


class DoclingLayoutParser:
    """PDF 레이아웃 분석 전처리기 (OCR 비활성화)."""

    def __init__(self, table_structure: bool = False) -> None:
        if not _DOCLING_AVAILABLE:
            logger.warning(
                "[DoclingParser] docling 패키지를 임포트할 수 없습니다. "
                "레이아웃 분석 비활성화. (설치: pip install docling)"
            )
            self._converter = None
            return

        pipeline_options = PdfPipelineOptions()       # type: ignore[possibly-undefined]
        pipeline_options.do_ocr = False               # OCR 완전 비활성화
        pipeline_options.do_table_structure = table_structure

        self._converter = DocumentConverter(          # type: ignore[possibly-undefined]
            format_options={
                InputFormat.PDF: PdfFormatOption(     # type: ignore[possibly-undefined]
                    pipeline_options=pipeline_options
                )
            }
        )
        logger.info("[DoclingParser] 초기화 완료 (OCR 비활성화)")

    @property
    def available(self) -> bool:
        return self._converter is not None

    @staticmethod
    def _get_page_count(pdf_path: str) -> int:
        """fitz로 PDF 페이지 수를 빠르게 확인합니다."""
        try:
            import fitz
            with fitz.open(pdf_path) as doc:
                return len(doc)
        except Exception:
            return 0

    def parse(self, pdf_path: str) -> dict[int, list[LayoutBlock]]:
        """PDF를 분석하여 페이지별 LayoutBlock 목록을 반환합니다.

        페이지 수가 _CHUNK_THRESHOLD 초과 시 _CHUNK_SIZE 단위로 분할 처리하여
        Docling 내부 std::bad_alloc 을 방지합니다.

        Returns:
            {page_number(1-based): [LayoutBlock, ...]}
            오류 시 빈 dict 반환 (폴백).
        """
        if not self.available:
            return {}

        total_pages = self._get_page_count(pdf_path)
        if total_pages > _CHUNK_THRESHOLD:
            logger.info(
                f"[DoclingParser] {total_pages}페이지 — "
                f"{_CHUNK_SIZE}페이지 단위 분할 처리 시작"
            )
            return self._parse_chunked(pdf_path, total_pages)

        return self._parse_single(pdf_path)

    def _parse_single(
        self, pdf_path: str, page_range: tuple[int, int] | None = None
    ) -> dict[int, list[LayoutBlock]]:
        """단일 convert() 호출로 레이아웃을 분석합니다."""
        kwargs: dict = {}
        if page_range is not None:
            kwargs["page_range"] = page_range
        try:
            result = self._converter.convert(pdf_path, **kwargs)  # type: ignore[union-attr]
            return self._convert(result)
        except Exception as exc:
            range_str = f" pages {page_range[0]}~{page_range[1]}" if page_range else ""
            logger.warning(f"[DoclingParser]{range_str} 분석 실패 — 해당 범위 스킵: {exc}")
            return {}

    def _parse_chunked(
        self, pdf_path: str, total_pages: int
    ) -> dict[int, list[LayoutBlock]]:
        """페이지를 _CHUNK_SIZE 단위로 나눠 순차 처리 후 결과를 병합합니다."""
        import gc
        merged: dict[int, list[LayoutBlock]] = {}
        start = 1
        chunk_no = 0

        while start <= total_pages:
            end = min(start + _CHUNK_SIZE - 1, total_pages)
            chunk_no += 1
            print(
                f"[DoclingParser] 청크 {chunk_no}: pages {start}~{end} / {total_pages}"
            )

            chunk_layout = self._parse_single(pdf_path, page_range=(start, end))
            merged.update(chunk_layout)

            # DoclingDocument 참조 해제 후 C++ 힙 회수 유도
            del chunk_layout
            gc.collect()

            start = end + 1

        total_blocks  = sum(len(v) for v in merged.values())
        total_figures = sum(1 for v in merged.values() for b in v if b.type == "figure")
        logger.info(
            f"[DoclingParser] 분할 처리 완료 — "
            f"{len(merged)}페이지, {total_blocks}블록 (Figure {total_figures}개)"
        )
        return merged

    # ── 변환 ──────────────────────────────────────────────────────────────────

    def _convert(self, result) -> dict[int, list[LayoutBlock]]:
        layout: dict[int, list[LayoutBlock]] = {}
        doc: DoclingDocument = result.document  # type: ignore[possibly-undefined]

        # 페이지 크기 사전 구축
        page_sizes: dict[int, tuple[float, float]] = {}
        for pg_no, pg_item in doc.pages.items():
            if pg_item.size:
                page_sizes[pg_no] = (pg_item.size.width, pg_item.size.height)
            else:
                page_sizes[pg_no] = (595.0, 842.0)  # A4 폴백

        # 1패스: caption bbox 수집 (page → list)
        caption_bboxes: dict[int, list[tuple[float, float, float, float]]] = {}
        for item, _ in doc.iterate_items():
            if getattr(item, "label", None) == DocItemLabel.CAPTION:  # type: ignore[possibly-undefined]
                for prov in getattr(item, "prov", []):
                    pg = prov.page_no
                    bb = self._prov_to_bbox(prov, page_sizes.get(pg, (595.0, 842.0)))
                    if bb:
                        caption_bboxes.setdefault(pg, []).append(bb)

        # 2패스: 전체 블록 변환
        for item, _ in doc.iterate_items():
            label = getattr(item, "label", None)
            block_type = _LABEL_MAP.get(label, "paragraph")  # type: ignore[possibly-undefined]

            for prov in getattr(item, "prov", []):
                pg = prov.page_no
                pw, ph = page_sizes.get(pg, (595.0, 842.0))
                bb = self._prov_to_bbox(prov, (pw, ph))
                if bb is None:
                    continue

                if block_type == "figure":
                    is_chart = label in _CHART_LABELS  # type: ignore[possibly-undefined]
                    has_cap = self._has_nearby_caption(bb, caption_bboxes.get(pg, []))
                    fig_type, ocr_skip = _classify_figure(bb, pw, ph, has_cap, is_chart)
                    block = LayoutBlock(
                        type="figure",
                        page=pg,
                        bbox=bb,
                        content="",
                        figure_type=fig_type,
                        has_caption=has_cap,
                        ocr_skip=ocr_skip,
                    )
                else:
                    text = getattr(item, "text", "") or ""
                    block = LayoutBlock(
                        type=block_type,
                        page=pg,
                        bbox=bb,
                        content=text.strip(),
                    )

                layout.setdefault(pg, []).append(block)

        total = sum(len(v) for v in layout.values())
        figures = sum(1 for v in layout.values() for b in v if b.type == "figure")
        skipped = sum(1 for v in layout.values() for b in v if b.type == "figure" and b.ocr_skip)
        logger.info(
            f"[DoclingParser] {len(layout)}페이지, {total}블록 "
            f"(Figure {figures}개, OCR스킵 {skipped}개)"
        )
        return layout

    # ── 헬퍼 ──────────────────────────────────────────────────────────────────

    def _prov_to_bbox(
        self,
        prov,
        page_size: tuple[float, float],
    ) -> tuple[float, float, float, float] | None:
        """ProvenanceItem.bbox (BoundingBox) → (x0, y0, x1, y1) top-left 원점.

        ProvenanceItem (docling_core) 필드:
            page_no : int
            bbox    : BoundingBox  (l, t, r, b, coord_origin)
            charspan: tuple[int, int]
        """
        try:
            bb = prov.bbox  # BoundingBox 객체
            l, t, r, b = bb.l, bb.t, bb.r, bb.b

            # coord_origin이 BOTTOMLEFT이면 top-left 좌표로 변환
            # BOTTOMLEFT: t = 박스 상단까지 높이, b = 박스 하단까지 높이 (바닥 기준)
            # TOPLEFT:   y0 = page_h - t,  y1 = page_h - b
            from docling_core.types.doc.base import CoordOrigin
            if getattr(bb, "coord_origin", None) == CoordOrigin.BOTTOMLEFT:
                ph = page_size[1]
                l, t, r, b = l, ph - t, r, ph - b

            # 정규화: 변환 후에도 역전이 남아 있을 수 있으므로 min/max 보정
            x0, y0, x1, y1 = float(l), float(t), float(r), float(b)
            return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        except Exception:
            return None

    def _has_nearby_caption(
        self,
        fig_bbox: tuple[float, float, float, float],
        caption_bboxes: list[tuple[float, float, float, float]],
        margin: float = 30.0,
    ) -> bool:
        """Figure bbox 근처(위/아래 margin pt 이내)에 caption이 있는지 확인."""
        x0, y0, x1, y1 = fig_bbox
        for cx0, cy0, cx1, cy1 in caption_bboxes:
            h_overlap = not (cx1 < x0 - margin or cx0 > x1 + margin)
            v_near = (cy0 >= y1 - margin and cy0 <= y1 + margin * 2) or \
                     (cy1 >= y0 - margin * 2 and cy1 <= y0 + margin)
            if h_overlap and v_near:
                return True
        return False


# ── 싱글턴 팩토리 ─────────────────────────────────────────────────────────────

_instance: DoclingLayoutParser | None = None


def get_parser() -> DoclingLayoutParser:
    """DoclingLayoutParser 싱글턴을 반환합니다."""
    global _instance
    if _instance is None:
        _instance = DoclingLayoutParser()
    return _instance
