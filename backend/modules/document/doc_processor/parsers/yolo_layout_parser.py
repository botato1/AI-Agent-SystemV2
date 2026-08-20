"""YOLO 문서 레이아웃 파서.

DocLayout-YOLO (DocLayNet 학습) 모델로 PDF 페이지를 분석하여
title / body / caption / table / figure 영역을 감지한다.

모델: juliozhao/DocLayout-YOLO-DocStructBench
클래스 (DocLayNet 10+1):
    0: Caption       → type="caption"
    1: Footnote      → type="caption"
    2: Formula       → type="body"
    3: List-item     → type="body"
    4: Page-footer   → type="caption"
    5: Page-header   → type="caption"
    6: Picture       → type="figure", figure_type="unknown"
    7: Section-header→ type="heading"
    8: Table         → type="figure", figure_type="table_image"
    9: Text          → type="body"
   10: Title         → type="title"
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from doc_processor.core.models import LayoutBlock

logger = logging.getLogger(__name__)

MODEL_ID = "Armaggheddon/yolo26-document-layout"
MODEL_FILENAME = "yolo26n_doc_layout.pt"
_RENDER_DPI = 150

# DocLayNet 클래스 인덱스 → 내부 type 매핑
_CLASS_MAP: dict[int, str] = {
    0: "caption",    # Caption
    1: "caption",    # Footnote
    2: "body",       # Formula
    3: "body",       # List-item
    4: "caption",    # Page-footer
    5: "caption",    # Page-header
    6: "figure",     # Picture
    7: "heading",    # Section-header
    8: "figure",     # Table
    9: "body",       # Text
    10: "title",     # Title
}

# figure일 때 figure_type 매핑
_FIGURE_TYPE_MAP: dict[int, str] = {
    6: "unknown",      # Picture → figure_classifier가 세분화
    8: "table_image",  # Table
}

# OCR 스킵 판단: 아주 작은 figure (면적 비율 < 1.5%) → 로고/아이콘
_LOGO_MAX_AREA_RATIO = 0.015


# 환경변수로 실험 가능 (예: YOLO_CONF=0.15 YOLO_IMGSZ=1600 YOLO_IOU=0.3 python ...)
_DEFAULT_CONF = float(os.environ.get("YOLO_CONF", "0.3"))
_DEFAULT_IOU = float(os.environ.get("YOLO_IOU", "0.45"))
_DEFAULT_IMGSZ = int(os.environ.get("YOLO_IMGSZ", "1280"))


class YOLOLayoutParser:
    """PDF 레이아웃 분석 전처리기 (YOLO 기반)."""

    def __init__(
        self,
        conf: float = _DEFAULT_CONF,
        iou: float = _DEFAULT_IOU,
        imgsz: int = _DEFAULT_IMGSZ,
    ) -> None:
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self._model = None
        print(f"[YOLOParser] conf={self.conf} iou={self.iou} imgsz={self.imgsz}")

    def _load(self):
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO
            from huggingface_hub import hf_hub_download

            # HuggingFace에서 가중치 다운로드
            weights_path = hf_hub_download(
                repo_id=MODEL_ID,
                filename=MODEL_FILENAME,
            )
            self._model = YOLO(weights_path)
            logger.info(f"[YOLOParser] 모델 로드 완료: {MODEL_ID}")
            print(f"[YOLOParser] 모델 로드 완료: {MODEL_ID}")
        except Exception as e:
            logger.error(f"[YOLOParser] 모델 로드 실패: {e}")
            self._model = None

    @property
    def available(self) -> bool:
        self._load()
        return self._model is not None

    def parse(self, pdf_path: str) -> dict[int, list[LayoutBlock]]:
        """PDF를 분석하여 페이지별 LayoutBlock 목록을 반환합니다.

        Returns:
            {page_number(1-based): [LayoutBlock, ...]}
            오류 시 빈 dict 반환 (폴백).
        """
        if not self.available:
            return {}

        try:
            import fitz
            import io
            from PIL import Image

            layout: dict[int, list[LayoutBlock]] = {}
            doc = fitz.open(pdf_path)
            zoom = _RENDER_DPI / 72.0
            mat = fitz.Matrix(zoom, zoom)

            for page_index in range(len(doc)):
                page_no = page_index + 1
                fitz_page = doc[page_index]
                pw = fitz_page.rect.width   # PDF pt 단위 페이지 너비
                ph = fitz_page.rect.height  # PDF pt 단위 페이지 높이

                # 페이지를 이미지로 렌더링
                pix = fitz_page.get_pixmap(matrix=mat, alpha=False)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                img_w, img_h = img.width, img.height

                # YOLO 추론
                results = self._model(
                    img,
                    conf=self.conf,
                    iou=self.iou,
                    imgsz=self.imgsz,
                    agnostic_nms=True,
                    verbose=False,
                )

                blocks: list[LayoutBlock] = []
                if results and len(results) > 0:
                    result = results[0]
                    for box in result.boxes:
                        cls_id = int(box.cls[0].item())
                        block_type = _CLASS_MAP.get(cls_id, "body")

                        # 픽셀 bbox → PDF pt 좌표 변환
                        x0_px, y0_px, x1_px, y1_px = box.xyxy[0].tolist()
                        x0 = x0_px / img_w * pw
                        y0 = y0_px / img_h * ph
                        x1 = x1_px / img_w * pw
                        y1 = y1_px / img_h * ph
                        bbox = (
                            min(x0, x1), min(y0, y1),
                            max(x0, x1), max(y0, y1),
                        )

                        if block_type == "figure":
                            fig_type = _FIGURE_TYPE_MAP.get(cls_id, "unknown")
                            area_ratio = (
                                (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                                / (pw * ph)
                                if pw * ph > 0 else 0.0
                            )
                            ocr_skip = (
                                fig_type == "unknown"
                                and area_ratio < _LOGO_MAX_AREA_RATIO
                            )
                            block = LayoutBlock(
                                type="figure",
                                page=page_no,
                                bbox=bbox,
                                content="",
                                figure_type=fig_type,
                                ocr_skip=ocr_skip,
                            )
                        else:
                            block = LayoutBlock(
                                type=block_type,
                                page=page_no,
                                bbox=bbox,
                                content="",
                            )
                        blocks.append(block)

                layout[page_no] = blocks
                figures = sum(1 for b in blocks if b.type == "figure")
                print(
                    f"  [YOLO] page={page_no}: {len(blocks)}블록 "
                    f"(figure {figures}개)"
                )
                if figures == 0 and blocks:
                    # figure가 0개인데 블록은 있는 경우 → 실제로 뭘로 분류됐는지 확인
                    detail = ", ".join(
                        f"{b.type}(area={((b.bbox[2]-b.bbox[0])*(b.bbox[3]-b.bbox[1]))/(pw*ph):.3f})"
                        for b in blocks
                    )
                    print(f"    [YOLO-DEBUG] page={page_no} 블록 상세: {detail}")

            doc.close()
            return layout

        except Exception as e:
            logger.warning(f"[YOLOParser] 분석 실패 — 폴백: {e}")
            return {}


# ── 싱글턴 팩토리 ─────────────────────────────────────────────────────────────

_instance: YOLOLayoutParser | None = None


def get_parser() -> YOLOLayoutParser:
    global _instance
    if _instance is None:
        _instance = YOLOLayoutParser()
    return _instance