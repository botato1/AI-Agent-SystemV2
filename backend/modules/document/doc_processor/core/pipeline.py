from __future__ import annotations

from pathlib import Path
from typing import Any

import time

import fitz
import pdfplumber

from doc_processor.classifiers import figure_classifier
from doc_processor.core.models import (
    ChartBlock,
    DocumentResult,
    ImageBlock,
    OcrStats,
    PageContent,
    PageResult,
    TableBlock,
)
from doc_processor.core.pdf_classifier import classify_pdf
from doc_processor.confidence.engine import ConfidenceEngine
from doc_processor.postprocess.processor import PostProcessor
from doc_processor.ocr.paddle_engine import PaddleEngine
from doc_processor.ocr import voter
from doc_processor.ocr.quality_scorer import calculate_quality_score, is_useful
from doc_processor.parsers.yolo_layout_parser import YOLOLayoutParser
from doc_processor.parsers.image_parser import (
    crop_layout_rect,
    crop_rect,
    get_figure_rects_from_layout,
    get_image_rects,
    is_valid_crop,
    normalize_bbox,
    render_page,
)
from doc_processor.ocr.table_ocr import get_or_create_tsr, run_table_ocr
from doc_processor.ocr.vl_engine import VLEngine as QwenVLEngine
from doc_processor.ocr.paddle_vl_1_6_engine import PaddleVL16Engine
from doc_processor.postprocess.vl_parser import parse as vl_parse
from doc_processor.parsers.table_parser import extract_tables
from doc_processor.parsers.text_parser import extract_text_blocks
from doc_processor.ocr.image_preprocessor import preprocess_for_ocr


class DocumentPipeline:
    def __init__(
        self,
        dpi: int = 220,
        min_image_px: int = 30,
        paddle_only_threshold: float = 0.80,
        use_docling: bool = True,
        debug_ocr: bool = False,
        ocr_upscale: float = 1.0,
    ) -> None:
        self.dpi = dpi
        self.min_image_px = min_image_px
        self.paddle_only_threshold = paddle_only_threshold
        self.debug_ocr = debug_ocr
        self.ocr_upscale = ocr_upscale          # True 이면 ImageBlock.debug 채움
        self._paddle: PaddleEngine | None = None
        self._tsr = None
        self._worst_ocr: list[dict] = []    # quality_score 하위 20건 (debug_ocr=True 시 사용)
        self._postprocessor = PostProcessor()
        self._confidence_engine = ConfidenceEngine()
        self._yolo = YOLOLayoutParser() if use_docling else None
        # VL 작업 큐 — 페이지 처리 중 쌓이고 _flush_vl_queue()에서 일괄 처리
        # {"image", "fig_type", "content", "bbox", "page_no", "area_ratio"}
        self._vl_queue: list[dict] = []

    def _save_worst_ocr_report(self, pdf_path: str) -> None:
        """quality_score 하위 20건을 JSON 파일로 저장합니다.

        저장 경로: {pdf_path}.ocr_worst20.json
        debug_ocr=True 일 때만 호출됩니다.
        """
        import json
        out_path = Path(pdf_path).with_suffix("") .with_suffix(".ocr_worst20.json")
        # quality_score 오름차순 정렬 (가장 낮은 품질이 먼저)
        sorted_worst = sorted(self._worst_ocr, key=lambda x: x["quality_score"])
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(sorted_worst, f, ensure_ascii=False, indent=2)
            print(f"[Pipeline] worst-20 OCR 리포트 저장: {out_path}")
        except Exception as e:
            print(f"[Pipeline] worst-20 리포트 저장 실패: {e}")

    @staticmethod
    def _ocr_quality(lines: list[str]) -> float:
        """Paddle OCR 결과의 품질을 추정합니다 (0.0 ~ 1.0).

        Surya 실행 여부를 결정하는 빠른 사전 판단용.
        기준: 라인 수 + 평균 길이 + 한글/영문 비율
        """
        if not lines:
            return 0.0

        import re
        total_chars = sum(len(l) for l in lines)
        if total_chars == 0:
            return 0.0

        all_text = " ".join(lines)
        alpha_korean = sum(1 for c in all_text if c.isalpha() or "가" <= c <= "힣")
        alpha_ratio = alpha_korean / len(all_text)

        line_score = min(len(lines) / 5.0, 1.0)       # 5줄 이상이면 만점
        len_score  = min(total_chars / 50.0, 1.0)      # 50자 이상이면 만점
        alpha_score = alpha_ratio

        return round((line_score + len_score + alpha_score) / 3.0, 3)

    # --- 모델은 최초 run() 호출 시 로딩 (지연 초기화) ---

    def _ensure_models(self) -> None:
        if self._paddle is None:
            print("[Pipeline] Loading PaddleOCR...")
            self._paddle = PaddleEngine()
        # surya 비활성화 (surya-ocr 0.20.0 Docker 의존성 문제)
        # if self._surya is None:
        #     print("[Pipeline] Loading Surya OCR...")
        #     self._surya = SuryaEngine()

    def run(self, pdf_path: str) -> DocumentResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        self._ensure_models()

        pdf_type = classify_pdf(pdf_path)
        print(f"[Pipeline] PDF type: {pdf_type}")

        # ── Docling 레이아웃 전처리 ──────────────────────────────────────────
        layout_map: dict[int, list] = {}
        if self._yolo and self._yolo.available:
            print("[Pipeline] YOLO 레이아웃 분석 중...")
            import time
            _t = time.perf_counter()
            layout_map = self._yolo.parse(pdf_path)
            _elapsed = time.perf_counter() - _t
            total_figures = sum(
                1 for blocks in layout_map.values()
                for b in blocks if b.type == "figure"
            )
            skip_figures = sum(
                1 for blocks in layout_map.values()
                for b in blocks if b.type == "figure" and b.ocr_skip
            )
            print(
                f"[Pipeline] YOLO 완료 ({_elapsed:.1f}s) / "
                f"Figure {total_figures}개 중 {skip_figures}개 OCR 스킵 (로고/배너)"
            )
        else:
            print("[Pipeline] YOLO 비활성화 / 기존 이미지 감지 사용")

        # OCR 통계 초기화 (문서 단위로 리셋)
        self._ocr_stats = OcrStats()
        self._worst_ocr = []                    # worst-20 리스트 초기화
        _pipeline_start = time.perf_counter()   # 전체 처리 시간 측정 시작

        doc = DocumentResult(source=str(path), pdf_type=pdf_type)

        with fitz.open(path) as fitz_doc, pdfplumber.open(path) as plumber_doc:
            total = len(fitz_doc)
            for page_index, fitz_page in enumerate(fitz_doc):
                page_no = page_index + 1
                print(f"[Pipeline] Page {page_no}/{total}")

                plumber_page = (
                    plumber_doc.pages[page_index]
                    if page_index < len(plumber_doc.pages)
                    else None
                )

                page_layout = layout_map.get(page_no, [])
                content = self._process_page(fitz_page, plumber_page, page_layout, page_no)
                content = self._postprocessor.process(content)

                doc.pages.append(PageResult(
                    page=page_no,
                    content=content,
                ))

        # VL 일괄 처리 (Paddle → 언로드 → Qwen → 언로드)
        self._flush_vl_queue(doc.pages)

        # 페이지별 신뢰도 계산 — VL 결과까지 모두 채워진 뒤에 채점
        for p in doc.pages:
            p.confidence = self._confidence_engine.compute(p.content)

        # 전체 처리 시간 기록
        self._ocr_stats.processing_time_sec = round(
            time.perf_counter() - _pipeline_start, 2
        )

        # 통계 집계 후 doc에 저장
        doc.ocr_stats = self._ocr_stats
        self._ocr_stats.print_summary(page_count=len(doc.pages))

        # debug_ocr=True 일 때 worst-20 리포트 저장
        if self.debug_ocr and self._worst_ocr:
            self._save_worst_ocr_report(pdf_path)

        return doc

    def _process_page(
        self,
        fitz_page: fitz.Page,
        plumber_page: Any,
        layout_blocks: list | None = None,
        page_no: int = 0,
    ) -> PageContent:
        content = PageContent()

        # 1. 텍스트 추출 — 항상 시도, 결과 없으면 빈 리스트
        content.text = extract_text_blocks(fitz_page)
        if content.text:
            print(f"  → 텍스트 블록: {len(content.text)}개")

        # 1-1. YOLO 레이아웃으로 텍스트 블록 style 덮어씌우기
        if layout_blocks:
            self._apply_yolo_styles(content.text, layout_blocks)

        # 2. 표 추출
        if plumber_page is not None:
            content.tables = extract_tables(plumber_page)
            if content.tables:
                print(f"  → 표: {len(content.tables)}개")

        # 3. 이미지/Figure OCR
        if layout_blocks:
            self._ocr_from_layout(fitz_page, layout_blocks, content, page_no)
        else:
            self._ocr_from_pymupdf(fitz_page, content, page_no)

        # 4. 보충 OCR: YOLO/PyMuPDF 처리 후에도 내용이 거의 없으면
        #    전체 페이지 OCR로 누락된 이미지 영역을 보충한다.
        has_real_text = len([t for t in content.text if len(t.text.strip()) > 3]) > 2
        has_ocr_text  = bool(content.images)
        has_tables    = bool(content.tables)
        has_pending_vl = any(task["page_no"] == page_no for task in self._vl_queue)
        if not has_real_text and not has_ocr_text and not has_tables and not has_pending_vl:
            print(f"  [SUPPLEMENT] 내용 희박 (텍스트<3 + 이미지0 + 표0) -> 전체 페이지 OCR 보충")
            self._ocr_full_page(fitz_page, content, page_no=page_no)
        elif has_pending_vl and not has_real_text and not has_ocr_text and not has_tables:
            print(f"  [SUPPLEMENT] 스킵 — VL 큐에 표/차트 처리 대기 중 (page={page_no})")

        return content

    # ── pdfplumber 표 중복 감지 ──────────────────────────────────────────────

    @staticmethod
    def _overlaps_plumber_table(
        fig_bbox: tuple[float, float, float, float],
        tables: list,
        threshold: float = 0.5,
    ) -> bool:
        """figure bbox가 pdfplumber 실제 표 bbox와 threshold 이상 겹치면 True.

        1행 1열 표는 pdfplumber 오탐으로 간주하여 제외합니다.
        """
        fx0, fy0, fx1, fy1 = fig_bbox
        fig_area = max((fx1 - fx0) * (fy1 - fy0), 1e-6)

        for tb in tables:
            if not tb.bbox or len(tb.bbox) < 4:
                continue
            # 실제 데이터 행/열 수 계산 (None 패딩 제외)
            real_rows = sum(
                1 for row in tb.data
                if any(cell is not None and str(cell).strip() for cell in row)
            )
            real_cols = max(
                (sum(1 for cell in row if cell is not None and str(cell).strip())
                 for row in tb.data),
                default=0,
            )
            # 1행 또는 1열 → pdfplumber 오탐으로 간주, 스킵
            if real_rows <= 1 or real_cols <= 1:
                continue
            tx0, ty0, tx1, ty1 = tb.bbox[0], tb.bbox[1], tb.bbox[2], tb.bbox[3]
            ix0, iy0 = max(fx0, tx0), max(fy0, ty0)
            ix1, iy1 = min(fx1, tx1), min(fy1, ty1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            overlap = (ix1 - ix0) * (iy1 - iy0)
            if overlap / fig_area >= threshold:
                return True
        return False

    @staticmethod
    def _is_contained(
        fig_bbox: tuple[float, float, float, float],
        accepted: list[tuple[float, float, float, float]],
        threshold: float = 0.9,
    ) -> bool:
        """fig_bbox가 이미 처리한(더 큰) figure 중 하나에 threshold 이상 포함되면 True."""
        fx0, fy0, fx1, fy1 = fig_bbox
        fig_area = max((fx1 - fx0) * (fy1 - fy0), 1e-6)

        for ax0, ay0, ax1, ay1 in accepted:
            ix0, iy0 = max(fx0, ax0), max(fy0, ay0)
            ix1, iy1 = min(fx1, ax1), min(fy1, ay1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            overlap = (ix1 - ix0) * (iy1 - iy0)
            if overlap / fig_area >= threshold:
                return True
        return False

    # ── YOLO style 적용 ──────────────────────────────────────────────────────

    @staticmethod
    def _apply_yolo_styles(text_blocks, layout_blocks) -> None:
        """YOLO 레이아웃 블록 bbox와 겹치는 TextBlock의 style을 덮어씁니다.

        YOLO가 감지한 title/heading/caption 영역에 속한 텍스트 블록은
        폰트 크기 기반 추정보다 YOLO 분류를 우선합니다.
        figure 블록은 텍스트 블록과 관계없으므로 스킵합니다.
        """
        # style 적용 대상 type만 필터
        style_blocks = [
            b for b in layout_blocks
            if b.type in ("title", "heading", "body", "caption")
        ]
        if not style_blocks:
            return

        for tb in text_blocks:
            tx0, ty0, tx1, ty1 = tb.bbox
            best_overlap = 0.0
            best_style = None

            for lb in style_blocks:
                lx0, ly0, lx1, ly1 = lb.bbox
                # 교집합 면적
                ix0, iy0 = max(tx0, lx0), max(ty0, ly0)
                ix1, iy1 = min(tx1, lx1), min(ty1, ly1)
                if ix1 <= ix0 or iy1 <= iy0:
                    continue
                overlap = (ix1 - ix0) * (iy1 - iy0)
                tb_area = max((tx1 - tx0) * (ty1 - ty0), 1e-6)
                ratio = overlap / tb_area
                if ratio > best_overlap:
                    best_overlap = ratio
                    best_style = lb.type

            # 텍스트 블록의 50% 이상이 YOLO 블록 안에 있으면 style 교체
            # 단, YOLO는 upgrade만 허용 (font 크기 기반 heading/title을 body로 내리지 않음)
            _STYLE_RANK = {"caption": 0, "body": 1, "heading": 2, "title": 3}
            if best_style and best_overlap >= 0.5:
                if _STYLE_RANK.get(best_style, 0) >= _STYLE_RANK.get(tb.style, 0):
                    tb.style = best_style

    # ── OCR 경로 A: YOLO Figure 블록 기반 ────────────────────────────────────

    def _ocr_from_layout(
        self,
        fitz_page: fitz.Page,
        layout_blocks: list,
        content: PageContent,
        page_no: int = 0,
    ) -> None:
        """YOLO가 감지한 Figure 블록만 OCR합니다."""
        page_size = (fitz_page.rect.width, fitz_page.rect.height)

        # ── YOLO가 이미 스킵한 figure 디버그 출력 ──────────────────────────────
        for b in layout_blocks:
            if b.type == "figure" and b.ocr_skip:
                nb = normalize_bbox(b.bbox)
                pw, ph = page_size
                w, h = nb[2]-nb[0], nb[3]-nb[1]
                ar = (w*h)/(pw*ph) if pw*ph > 0 else 0.0
                print(
                    f"  [FIGURE] page={page_no} "
                    f"bbox=({b.bbox[0]:.1f},{b.bbox[1]:.1f},{b.bbox[2]:.1f},{b.bbox[3]:.1f}) "
                    f"normalized=({nb[0]:.1f},{nb[1]:.1f},{nb[2]:.1f},{nb[3]:.1f}) "
                    f"docling_type={b.figure_type} area_ratio={ar:.4f} "
                    f"decision=SKIP(yolo)"
                )

        figure_pairs = get_figure_rects_from_layout(layout_blocks)

        if not figure_pairs:
            if not content.text and not content.tables:
                print("  → YOLO Figure 없음 + 텍스트/표 없음, 페이지 전체 OCR")
                self._ocr_full_page(fitz_page, content, page_no=page_no)
            else:
                print(f"  → YOLO: OCR 대상 Figure 없음, 스킵")
            return

        print(f"  → YOLO Figure {len(figure_pairs)}개 → Worthy 평가")
        page_image = render_page(fitz_page, dpi=self.dpi)

        # ── 1단계: 유효 crop만 골라 분류 (아직 OCR은 안 함) ─────────────────
        candidates: list[dict] = []
        for block, rect in figure_pairs:
            nb = normalize_bbox(block.bbox)

            # pdfplumber가 이미 잡은 실제 표 영역과 50% 이상 겹치면 스킵
            if self._overlaps_plumber_table(nb, content.tables):
                print(f"  [SKIP] pdfplumber 표와 중복 영역 → VL 스킵 (bbox={nb})")
                continue

            cropped = crop_layout_rect(page_image, nb, dpi=self.dpi)
            if not is_valid_crop(cropped):
                continue

            # ── Figure 분류 ───────────────────────────────────────────────────
            # YOLO Table(class 8)도 격자선 검증 후 chart로 재분류 가능
            fig_type = figure_classifier.classify(
                cropped,
                yolo_table=(block.figure_type == "table_image"),
            )
            candidates.append({
                "block": block, "bbox": nb, "cropped": cropped, "fig_type": fig_type,
            })

        # ── 2단계: diagram 타입끼리만 중복(포함관계) 제거 ────────────────────
        # chart/table_image는 같은 영역이 여러 크기로 잡혀도 각각 유의미한
        # 개별 패널일 수 있어 건드리지 않음. diagram(인포그래픽)만 같은 이미지가
        # 큰 박스/작은 박스로 중복 검출되는 경우가 있어 큰 쪽만 남긴다.
        diagram_candidates = [c for c in candidates if c["fig_type"] == "diagram"]
        diagram_candidates.sort(
            key=lambda c: (c["bbox"][2]-c["bbox"][0]) * (c["bbox"][3]-c["bbox"][1]),
            reverse=True,
        )
        accepted_diagram_bboxes: list[tuple[float, float, float, float]] = []
        dropped_ids = set()
        for c in diagram_candidates:
            if self._is_contained(c["bbox"], accepted_diagram_bboxes):
                print(f"  [SKIP] 더 큰 diagram에 포함된 중복 영역 → 스킵 (bbox={c['bbox']})")
                dropped_ids.add(id(c))
                continue
            accepted_diagram_bboxes.append(c["bbox"])

        # ── 2-b단계: 개별 figure 여러 개를 통째로 감싸는 "컨테이너" chart 제거 ──
        # 다중 패널 페이지에서 왼쪽/오른쪽 개별 차트와 별개로 페이지 절반을 덮는
        # 큰 박스가 함께 검출되는 경우, 큰 박스는 개별 패널과 중복 데이터를
        # 만들므로 버린다. 개별 후보를 2개 이상 포함할 때만 컨테이너로 판정
        # (1개 포함은 부분/전체 크롭 관계일 수 있어 유지).
        # diagram 큰 박스는 위 2단계의 "큰 쪽 유지" 규칙 대상이므로 제외.
        for big in candidates:
            if id(big) in dropped_ids or big["fig_type"] != "chart":
                continue
            contained = sum(
                1 for other in candidates
                if other is not big
                and id(other) not in dropped_ids
                and self._is_contained(other["bbox"], [big["bbox"]])
            )
            if contained >= 2:
                print(
                    f"  [SKIP] 개별 figure {contained}개를 감싸는 컨테이너 chart → 스킵 "
                    f"(bbox={big['bbox']})"
                )
                dropped_ids.add(id(big))

        # ── 3단계: 남은 후보를 실제 OCR로 ────────────────────────────────────
        pw, ph = page_size
        for c in candidates:
            if id(c) in dropped_ids:
                continue
            block, nb, cropped, fig_type = c["block"], c["bbox"], c["cropped"], c["fig_type"]
            w, h = nb[2]-nb[0], nb[3]-nb[1]
            ar = (w*h)/(pw*ph) if pw*ph > 0 else 0.0

            print(
                f"  [FIGURE] page={page_no} "
                f"bbox=({block.bbox[0]:.1f},{block.bbox[1]:.1f},{block.bbox[2]:.1f},{block.bbox[3]:.1f}) "
                f"yolo_hint={block.figure_type} type={fig_type} area_ratio={ar:.4f} "
                f"decision=OCR"
            )

            ocr_result = self._run_ocr(
                cropped, tag=f"[{fig_type}]",
                fig_type=fig_type, area_ratio=ar,
                page_no=page_no,
                content=content, bbox=list(nb),
            )
            if ocr_result is None:
                # VL 큐에 추가된 경우 → attempt_count는 _flush_vl_queue에서 집계
                continue

            self._ocr_stats.attempt_count += 1
            self._ocr_stats.success_count += 1
            self._append_ocr_result(content, ocr_result, list(nb), page_no)

    # ── OCR 경로 B: PyMuPDF 이미지 블록 기반 (Docling 없을 때 폴백) ──────────

    def _ocr_from_pymupdf(
        self,
        fitz_page: fitz.Page,
        content: PageContent,
        page_no: int = 0,
    ) -> None:
        """기존 방식 — PyMuPDF 이미지 블록 감지 후 OCR."""
        image_rects = get_image_rects(fitz_page)

        if image_rects:
            print(f"  → 이미지 블록 {len(image_rects)}개 → Worthy 평가")
            page_image = render_page(fitz_page, dpi=self.dpi)
            page_size  = (fitz_page.rect.width, fitz_page.rect.height)

            for rect in image_rects:
                raw_bbox = (rect.x0, rect.y0, rect.x1, rect.y1)
                nb = normalize_bbox(raw_bbox)
                cropped = crop_rect(page_image, rect, dpi=self.dpi)
                if not is_valid_crop(cropped):
                    continue

                fig_type = figure_classifier.classify(cropped)
                pw, ph = page_size
                w, h = nb[2]-nb[0], nb[3]-nb[1]
                ar = (w*h)/(pw*ph) if pw*ph > 0 else 0.0

                print(
                    f"  [FIGURE] page={page_no} "
                    f"bbox=({raw_bbox[0]:.1f},{raw_bbox[1]:.1f},{raw_bbox[2]:.1f},{raw_bbox[3]:.1f}) "
                    f"type={fig_type} area_ratio={ar:.4f} "
                    f"decision=OCR"
                )

                ocr_result = self._run_ocr(
                    cropped, tag=f"[{fig_type}]",
                    fig_type=fig_type, area_ratio=ar,
                    page_no=page_no,
                    content=content, bbox=list(nb),
                )
                if ocr_result is None:
                    # VL 큐에 추가된 경우 → attempt_count는 _flush_vl_queue에서 집계
                    continue

                self._ocr_stats.attempt_count += 1
                self._ocr_stats.success_count += 1
                self._append_ocr_result(content, ocr_result, list(nb), page_no)

        elif not content.text and not content.tables:
            print("  → 텍스트/표 없음, 페이지 전체 OCR")
            self._ocr_full_page(fitz_page, content, page_no=page_no)
        else:
            print("  → 이미지 없음, OCR 스킵")

    # ── 페이지 전체 OCR (스캔 페이지용) ──────────────────────────────────────

    def _ocr_full_page(self, fitz_page: fitz.Page, content: PageContent, page_no: int = 0) -> None:
        self._ocr_stats.attempt_count += 1   # full_page OCR도 시도 횟수에 포함
        page_image = render_page(fitz_page, dpi=self.dpi)
        ocr_result = self._run_ocr(page_image, fig_type="full_page", area_ratio=1.0, page_no=page_no)
        if ocr_result is None:
            return
        self._ocr_stats.success_count += 1   # full_page 성공 집계
        w, h = page_image.size
        self._append_ocr_result(content, ocr_result, [0.0, 0.0, float(w), float(h)], page_no)

    # ── VL 일괄 처리 ─────────────────────────────────────────────────────────

    def _flush_vl_queue(self, pages: list) -> None:
        """VL 큐를 Paddle(표) → Qwen(차트) 순서로 처리합니다.

        각 모델을 쓴 후 즉시 언로드하여 VRAM을 절약합니다.
        PostProcessor가 새 PageContent 객체를 반환하므로,
        VL 결과는 page_no로 PageResult를 찾아 post-processed content에 직접 씁니다.
        """
        import torch

        # page_no → post-processed PageContent 매핑
        page_content_map = {p.page: p.content for p in pages}

        table_tasks   = [t for t in self._vl_queue if t["fig_type"] == "table_image"]
        chart_tasks   = [t for t in self._vl_queue if t["fig_type"] == "chart"]
        diagram_tasks = [t for t in self._vl_queue if t["fig_type"] == "diagram"]
        self._vl_queue.clear()

        def _process_tasks(engine, tasks: list, source_name: str) -> None:
            for task in tasks:
                # post-processed content로 교체
                task["content"] = page_content_map.get(task["page_no"], task["content"])
                self._ocr_stats.attempt_count += 1
                raw = engine.run(task["image"], fig_type=task["fig_type"])
                if not raw.strip():
                    print(f"    [VL-{source_name}] 결과 없음 (page={task['page_no']})")
                    self._ocr_stats.empty_count += 1
                    continue
                self._ocr_stats.table_tsr_count += 1
                self._ocr_stats.useful_count += 1
                self._ocr_stats.accumulate_quality_score(1.0)
                result: dict = {
                    "text":          raw,
                    "confidence":    1.0,
                    "quality_score": 1.0,
                    "sources":       [source_name],
                    "paddle_lines":  [],
                    "surya_lines":   [],
                    "vl_fig_type":   task["fig_type"],
                }
                self._ocr_stats.success_count += 1
                self._append_ocr_result(
                    task["content"], result, task["bbox"], task["page_no"]
                )

        # ── Pass 1: PaddleOCR-VL-1.6 (표) ─────────────────────────────────
        if table_tasks:
            print(f"\n[VL] Paddle-VL 로드 → 표 {len(table_tasks)}건 처리")
            paddle_engine = PaddleVL16Engine()
            _process_tasks(paddle_engine, table_tasks, "paddle-vl-1.6")
            del paddle_engine
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("[VL] Paddle-VL 언로드 완료")

        # ── Pass 2: Qwen3-VL-8B (차트 + 다이어그램/인포그래픽) ───────────────
        if chart_tasks or diagram_tasks:
            print(
                f"\n[VL] Qwen3-VL 로드 → 차트 {len(chart_tasks)}건, "
                f"다이어그램 {len(diagram_tasks)}건 처리"
            )
            qwen_engine = QwenVLEngine()
            _process_tasks(qwen_engine, chart_tasks, "qwen3-vl")
            _process_tasks(qwen_engine, diagram_tasks, "qwen3-vl-diagram")
            del qwen_engine
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print("[VL] Qwen3-VL 언로드 완료")

    @staticmethod
    def _find_caption_above(text_blocks, bbox: list[float], max_gap: float = 60.0) -> str:
        """차트 bbox 바로 위에 있는 heading/body 텍스트를 제목 후보로 반환합니다."""
        if not bbox or len(bbox) < 4:
            return ""
        cx0, cy0, cx1, _ = bbox
        best_text = ""
        best_dist = float("inf")
        import re as _re
        _CITE_PREFIXES = ("자료", "출처", "주:", "주1", "※", "▪", "Source")
        _DATE_PAT = _re.compile(r"^'?\d{2}\.\d")
        for block in text_blocks:
            text = block.text.strip()
            if not text:
                continue
            if block.style == "caption":
                if text.startswith(_CITE_PREFIXES):
                    continue
                if _DATE_PAT.match(text):  # 날짜 축 레이블 ('20.3 등)
                    continue
            if len(text) > 80:  # 본문 단락은 제목 후보에서 제외
                continue
            bx0, by0, bx1, by1 = block.bbox
            if by1 > cy0:
                continue
            # 수평으로 전혀 겹치지 않는 블록은 제외 — heading도 예외 없음.
            # (2단 레이아웃에서 옆 컬럼의 제목을 가져오는 오류 방지)
            if bx1 < cx0 or bx0 > cx1:
                continue
            # heading은 수직 간격 허용치만 완화 (제목과 차트 사이에 범례 등이 낄 수 있음)
            effective_gap = max_gap * 2.5 if block.style == "heading" else max_gap
            dist = cy0 - by1
            # gap을 넘는 후보는 여기서 즉시 제외 — 과거에는 최근접 후보를 먼저 뽑고
            # 마지막에 한 번만 gap을 검사해서, gap 밖의 가까운 body가 gap 안의
            # heading을 밀어내고 결과를 빈 문자열로 만드는 버그가 있었음.
            if dist > effective_gap:
                continue
            if dist < best_dist:
                best_dist = dist
                best_text = text
        return best_text

    def _append_ocr_result(
        self,
        content: PageContent,
        ocr_result: dict,
        bbox: list[float],
        page_no: int,
    ) -> None:
        """OCR 결과를 fig_type에 따라 content.images / tables / charts에 추가합니다."""
        vl_fig_type = ocr_result.get("vl_fig_type")

        if vl_fig_type == "diagram":
            parsed = vl_parse(ocr_result["text"], vl_fig_type, page_no)
            content.images.append(ImageBlock(
                bbox=bbox,
                ocr_text=parsed["raw_text"],
                voting_confidence=ocr_result["confidence"],
                source_engines=ocr_result["sources"],
                paddle_lines=ocr_result["paddle_lines"],
                surya_lines=ocr_result.get("surya_lines", []),
                quality_score=ocr_result["quality_score"],
                image_type="diagram",
            ))
        elif vl_fig_type in ("table_image", "chart"):
            parsed = vl_parse(ocr_result["text"], vl_fig_type, page_no)
            if vl_fig_type == "table_image":
                content.tables.append(TableBlock(
                    data=[],
                    markdown=parsed["markdown"],
                    bbox=bbox,
                ))
            else:
                vl_title = parsed.get("title", "")
                nearby_title = self._find_caption_above(content.text, bbox)
                title = nearby_title or vl_title
                content.charts.append(ChartBlock(
                    bbox=bbox,
                    description=parsed["raw_text"],
                    extracted_data={
                        "title": title,
                        "data":  parsed.get("data", []),
                        "raw_text": parsed["raw_text"],
                    },
                ))
        else:
            content.images.append(ImageBlock(
                bbox=bbox,
                ocr_text=ocr_result["text"],
                voting_confidence=ocr_result["confidence"],
                source_engines=ocr_result["sources"],
                paddle_lines=ocr_result["paddle_lines"],
                surya_lines=ocr_result.get("surya_lines", []),
                quality_score=ocr_result["quality_score"],
                debug=ocr_result.get("debug"),
            ))

    # ── OCR 실행 공통 로직 ────────────────────────────────────────────────────

    def _run_ocr(
        self,
        image,
        tag: str = "",
        fig_type: str = "",
        area_ratio: float = 0.0,
        page_no: int = 0,
        content: PageContent | None = None,
        bbox: list[float] | None = None,
    ) -> dict | None:
        """Paddle(+Surya) OCR을 실행하고 결과 dict를 반환합니다.

        table_image / chart는 즉시 실행하지 않고 _vl_queue에 추가합니다.
        _flush_vl_queue()에서 Paddle → Qwen 순으로 일괄 처리합니다.
        """
        # ── table_image / chart / diagram → VL 큐에 추가 (즉시 실행 안 함) ───
        if fig_type in ("table_image", "chart", "diagram"):
            print(f"    [OCR{tag}] VL 큐 추가 (fig_type={fig_type})")
            self._vl_queue.append({
                "image":      image,
                "fig_type":   fig_type,
                "content":    content,
                "bbox":       bbox or [],
                "page_no":    page_no,
                "area_ratio": area_ratio,
            })
            return None

        # ── 전처리 + 업스케일 (table_image/chart 제외 경로에만 적용) ───────────
        image = preprocess_for_ocr(image, upscale=self.ocr_upscale)

        paddle_lines = self._paddle.run(image)  # type: ignore[union-attr]
        paddle_quality = self._ocr_quality(paddle_lines)

        _SURYA_SKIP_TYPES = {"diagram"}

        if fig_type in _SURYA_SKIP_TYPES:
            print(f"    [OCR{tag}] Paddle only (fig_type={fig_type})")
            result = voter.vote(paddle_lines, [], threshold=0.0)
            result["sources"] = ["paddle_only"]
            result["paddle_lines"] = paddle_lines
            result["surya_lines"] = []
            self._ocr_stats.paddle_only_count += 1
            self._ocr_stats.chart_paddle_only_count += 1
            voting_path = "paddle_only_chart"
        else:
            # surya 비활성화 — paddle only로 처리 (surya-ocr 0.20.0 Docker 의존성 문제)
            print(f"    [OCR{tag}] Paddle only (quality={paddle_quality:.2f})")
            result = voter.vote(paddle_lines, [], threshold=0.0)
            result["sources"] = ["paddle_only"]
            result["paddle_lines"] = paddle_lines
            result["surya_lines"] = []
            self._ocr_stats.paddle_only_count += 1
            voting_path = "paddle_only"

        if not result["text"].strip():
            print(f"    [OCR{tag}] 텍스트 없음 (빈 이미지)")
            self._ocr_stats.empty_count += 1
            return None
        if result.get("filtered"):
            print(f"    [OCR{tag}] voter 필터 제거: {result['filter_reason']}")
            self._ocr_stats.filtered_count += 1
            return None

        # ── quality_score 계산 (항상, 자동 필터링 없음) ──────────────────────
        voted_text = result["text"]
        q_score = calculate_quality_score(voted_text)
        result["quality_score"] = q_score
        print(f"    [OCR{tag}] quality_score={q_score:.3f}")

        # useful / garbage 분류 (관측용, 자동 필터 없음)
        if is_useful(voted_text):
            self._ocr_stats.useful_count += 1
        else:
            self._ocr_stats.garbage_count += 1

        # avg_quality_score 누적
        self._ocr_stats.accumulate_quality_score(q_score)

        # ── 엔진별 문자/라인 수 계산 ─────────────────────────────────────────
        paddle_lines = result["paddle_lines"]
        surya_lines  = result.get("surya_lines", [])

        paddle_char_count = sum(len(l) for l in paddle_lines)
        surya_char_count  = sum(len(l) for l in surya_lines)
        voted_char_count  = len(voted_text.replace("\n", ""))

        paddle_line_count = len(paddle_lines)
        surya_line_count  = len(surya_lines)
        voted_line_count  = len([l for l in voted_text.split("\n") if l.strip()])

        # 엔진별 문자 수 통계 누적 (항상)
        self._ocr_stats.accumulate_char_counts(
            paddle_chars=paddle_char_count,
            surya_chars=surya_char_count,
            voted_chars=voted_char_count,
        )

        # ── debug 정보 수집 (debug_ocr=True 일 때만) ─────────────────────────
        if self.debug_ocr:
            result["debug"] = {
                "paddle_raw":       paddle_lines,
                "surya_raw":        surya_lines,
                "voted_text":       voted_text,        # PostProcess 전 텍스트
                "paddle_quality":   round(paddle_quality, 3),
                "voting_path":      voting_path,
                "filter_reason":    result.get("filter_reason"),
                "quality_score":    q_score,
                "fig_type":         fig_type,
                "area_ratio":       round(area_ratio, 4),
                "image_width":      image.width,
                "image_height":     image.height,
                "image_area":       image.width * image.height,
                # ── 작업 2: 엔진별 문자/라인 수 ──────────────────────────────
                "paddle_char_count": paddle_char_count,
                "surya_char_count":  surya_char_count,
                "voted_char_count":  voted_char_count,
                "paddle_line_count": paddle_line_count,
                "surya_line_count":  surya_line_count,
                "voted_line_count":  voted_line_count,
            }

            # ── 작업 4: worst-20 수집 ─────────────────────────────────────────
            entry = {
                "page":          page_no,
                "fig_type":      fig_type,
                "quality_score": q_score,
                "paddle_raw":    "\n".join(paddle_lines),
                "surya_raw":     "\n".join(surya_lines),
                "voted_text":    voted_text,
                "final_text":    None,          # processor.py 완료 후 채울 수 없으므로 None
            }
            self._worst_ocr.append(entry)
            # quality_score 오름차순으로 상위 20개만 유지
            self._worst_ocr.sort(key=lambda x: x["quality_score"])
            if len(self._worst_ocr) > 20:
                self._worst_ocr = self._worst_ocr[:20]

        return result