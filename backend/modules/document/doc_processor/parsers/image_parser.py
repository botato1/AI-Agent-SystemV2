from __future__ import annotations

from typing import TYPE_CHECKING

import fitz
from PIL import Image

if TYPE_CHECKING:
    from doc_processor.core.models import LayoutBlock

# ── 픽셀 단위 최소 크기 (크롭 후 검사) ──────────────────────────────────────
_MIN_WIDTH_PX  = 80
_MIN_HEIGHT_PX = 40


def get_image_rects(fitz_page: fitz.Page) -> list[fitz.Rect]:
    """페이지의 모든 이미지 블록 Rect를 반환합니다.

    크기/타입 필터는 FigureClassifier에서 수행합니다.
    여기서는 이미지 블록 위치 감지만 담당합니다.
    """
    blocks = fitz_page.get_text("dict")["blocks"]
    rects: list[fitz.Rect] = []

    for b in blocks:
        if b.get("type") != 1:
            continue
        rects.append(fitz.Rect(b["bbox"]))

    return rects


def render_page(fitz_page: fitz.Page, dpi: int = 220) -> Image.Image:
    """PDF 페이지를 PIL Image로 렌더링합니다."""
    pix = fitz_page.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def crop_rect(page_image: Image.Image, rect: fitz.Rect, dpi: int = 220) -> Image.Image:
    """PDF 좌표계 Rect를 픽셀 좌표로 변환해 이미지를 크롭합니다."""
    scale = dpi / 72.0
    x0 = int(rect.x0 * scale)
    y0 = int(rect.y0 * scale)
    x1 = int(rect.x1 * scale)
    y1 = int(rect.y1 * scale)
    return page_image.crop((x0, y0, x1, y1))


def normalize_bbox(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """bbox 좌표를 (left, top, right, bottom) 형태로 정규화합니다.

    좌표 변환 버그나 좌표계 불일치로 x0>x1 또는 y0>y1이 들어와도
    항상 width≥0, height≥0을 보장합니다.
    """
    x0, y0, x1, y1 = bbox
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def is_valid_crop(image: Image.Image) -> bool:
    """크롭된 이미지가 OCR 수행할 만한 크기인지 확인합니다."""
    return image.width >= _MIN_WIDTH_PX and image.height >= _MIN_HEIGHT_PX


def crop_layout_rect(
    page_image: Image.Image,
    bbox: tuple[float, float, float, float],
    dpi: int = 220,
) -> Image.Image:
    """LayoutBlock bbox (pt, top-left origin) → PIL 크롭 이미지.

    bbox가 역전된 경우(y0 > y1) 자동으로 min/max 정렬합니다.
    """
    scale = dpi / 72.0
    x0, y0, x1, y1 = bbox
    # 방어: 좌표 역전 방지
    left   = int(min(x0, x1) * scale)
    top    = int(min(y0, y1) * scale)
    right  = int(max(x0, x1) * scale)
    bottom = int(max(y0, y1) * scale)
    return page_image.crop((left, top, right, bottom))


def get_figure_rects_from_layout(
    layout_blocks: "list[LayoutBlock]",
) -> list[tuple["LayoutBlock", fitz.Rect]]:
    """Docling LayoutBlock 중 figure 타입만 골라 (block, fitz.Rect) 쌍을 반환합니다.

    ocr_skip=True 블록은 이미 제외되어 반환되지 않습니다.

    Returns:
        [(LayoutBlock, fitz.Rect), ...]  — OCR 대상 figure 목록
    """
    result: list[tuple[LayoutBlock, fitz.Rect]] = []
    for block in layout_blocks:
        if block.type != "figure":
            continue
        if block.ocr_skip:
            continue
        x0, y0, x1, y1 = block.bbox
        rect = fitz.Rect(x0, y0, x1, y1)
        result.append((block, rect))
    return result
