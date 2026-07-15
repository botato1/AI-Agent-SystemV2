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
from doc_processor.postprocess.processor import PostProcessor
from doc_processor.ocr.paddle_engine import PaddleEngine
from doc_processor.ocr import voter
from doc_processor.ocr.worthy_score import calculate_ocr_worthy_score, OCR_THRESHOLD, AMBIGUOUS_TYPES
from doc_processor.ocr.quality_scorer import calculate_quality_score, is_useful
from doc_processor.parsers.docling_parser import DoclingLayoutParser
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
from doc_processor.ocr.vl_engine import VLEngine
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
        self._tsr = None                    # TableStructureRecognition (table_image 최초 사용 시 로드)
        self._vl: VLEngine | None = None    # PaddleOCR-VL (표/차트 전용)
        self._worst_ocr: list[dict] = []    # quality_score 하위 20건 (debug_ocr=True 시 사용)
        self._postprocessor = PostProcessor()
        # Docling 레이아웃 파서 (선택적)
        self._docling = DoclingLayoutParser() if use_docling else None

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

    def run(self, pdf_path: str) -> DocumentResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        self._ensure_models()

        pdf_type = classify_pdf(pdf_path)
        print(f"[Pipeline] PDF type: {pdf_type}")

        # ── Docling 레이아웃 전처리 ──────────────────────────────────────────
        layout_map: dict[int, list] = {}
        if self._docling and self._docling.available:
            print("[Pipeline] Docling 레이아웃 분석 중...")
            import time
            _t = time.perf_counter()
            layout_map = self._docling.parse(pdf_path)
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
                f"[Pipeline] Docling 완료 ({_elapsed:.1f}s) / "
                f"Figure {total_figures}개 중 {skip_figures}개 OCR 스킵 (로고/배너)"
            )
        else:
            print("[Pipeline] Docling 비활성화 / 기존 이미지 감지 사용")

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

        # 4. 보충 OCR: Docling/PyMuPDF 처리 후에도 내용이 거의 없으면
        #    전체 페이지 OCR로 누락된 이미지 영역을 보충한다.
        #    (Docling이 일부 영역만 figure로 잡고 나머지를 놓친 경우 대응)
        has_real_text = len([t for t in content.text if len(t.text.strip()) > 3]) > 2
        has_ocr_text  = bool(content.images)
        has_tables    = bool(content.tables)
        if not has_real_text and not has_ocr_text and not has_tables:
            print(f"  [SUPPLEMENT] 내용 희박 (텍스트<3 + 이미지0 + 표0) -> 전체 페이지 OCR 보충")
            self._ocr_full_page(fitz_page, content, page_no=page_no)

        return content

    # ── OCR 경로 A: Docling Figure 블록 기반 ──────────────────────────────────

    def _ocr_from_layout(
        self,
        fitz_page: fitz.Page,
        layout_blocks: list,
        content: PageContent,
        page_no: int = 0,
    ) -> None:
        """Docling이 감지한 Figure 블록만 OCR합니다."""
        page_size = (fitz_page.rect.width, fitz_page.rect.height)

        # ── Docling이 이미 스킵한 figure 디버그 출력 ─────────────────────────
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
                    f"decision=SKIP(docling)"
                )

        figure_pairs = get_figure_rects_from_layout(layout_blocks)

        if not figure_pairs:
            if not content.text and not content.tables:
                print("  → Docling Figure 없음 + 텍스트/표 없음, 페이지 전체 OCR")
                self._ocr_full_page(fitz_page, content, page_no=page_no)
            else:
                print(f"  → Docling: OCR 대상 Figure 없음, 스킵")
            return

        print(f"  → Docling Figure {len(figure_pairs)}개 → Worthy 평가")
        page_image = render_page(fitz_page, dpi=self.dpi)

        for block, rect in figure_pairs:
            nb = normalize_bbox(block.bbox)
            cropped = crop_layout_rect(page_image, nb, dpi=self.dpi)
            if not is_valid_crop(cropped):
                continue

            # ── Figure 분류 ───────────────────────────────────────────────────
            fig_type, pix_stats = figure_classifier.classify(
                cropped, nb, page_size, docling_hint=block.figure_type
            )
            pw, ph = page_size
            w, h = nb[2]-nb[0], nb[3]-nb[1]
            ar = (w*h)/(pw*ph) if pw*ph > 0 else 0.0
            ed = pix_stats.get("edge_density", 0.0)
            mg = pix_stats.get("mean_gray", 0.0)
            dk = pix_stats.get("dark_ratio", 0.0)
            self._ocr_stats.attempt_count += 1

            # ── OCR 여부 결정 (타입 기반) ────────────────────────────────────
            # 확정 OCR 타입: 분류기가 텍스트 있음을 확인한 경우
            if fig_type in ("text_image", "table_image", "diagram"):
                decision = "OCR"
                score = 1.0
            # 확정 SKIP 타입: 텍스트 없을 가능성이 높은 경우
            elif fig_type in ("logo", "product", "photo"):
                decision = "SKIP"
                score = 0.0
            # 애매한 타입: worthy_score 보조 판단
            else:  # unknown, chart
                score = calculate_ocr_worthy_score(fig_type, nb, page_size, pix_stats)
                decision = "OCR" if score >= OCR_THRESHOLD else "SKIP"

            print(
                f"  [FIGURE] page={page_no} "
                f"bbox=({block.bbox[0]:.1f},{block.bbox[1]:.1f},{block.bbox[2]:.1f},{block.bbox[3]:.1f}) "
                f"type={fig_type} area_ratio={ar:.4f} "
                f"mg={mg:.1f} dk={dk:.3f} ed={ed:.3f} "
                f"score={score:.3f} decision={decision}"
            )

            if decision == "SKIP":
                self._ocr_stats.skip_count += 1
                continue

            ocr_result = self._run_ocr(
                cropped, tag=f"[{fig_type}]",
                fig_type=fig_type, area_ratio=ar,
                page_no=page_no,
            )
            if ocr_result is None:
                continue

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

                fig_type, pix_stats = figure_classifier.classify(
                    cropped, nb, page_size
                )
                pw, ph = page_size
                w, h = nb[2]-nb[0], nb[3]-nb[1]
                ar = (w*h)/(pw*ph) if pw*ph > 0 else 0.0
                self._ocr_stats.attempt_count += 1

                # ── OCR 여부 결정 (타입 기반) ─────────────────────────────────
                if fig_type in ("text_image", "table_image", "diagram"):
                    decision = "OCR"
                    score = 1.0
                elif fig_type in ("logo", "product", "photo"):
                    decision = "SKIP"
                    score = 0.0
                else:  # unknown, chart
                    score = calculate_ocr_worthy_score(fig_type, nb, page_size, pix_stats)
                    decision = "OCR" if score >= OCR_THRESHOLD else "SKIP"

                print(
                    f"  [FIGURE] page={page_no} "
                    f"bbox=({raw_bbox[0]:.1f},{raw_bbox[1]:.1f},{raw_bbox[2]:.1f},{raw_bbox[3]:.1f}) "
                    f"type={fig_type} area_ratio={ar:.4f} "
                    f"score={score:.3f} decision={decision}"
                )

                if decision == "SKIP":
                    self._ocr_stats.skip_count += 1
                    continue

                ocr_result = self._run_ocr(
                    cropped, tag=f"[{fig_type}]",
                    fig_type=fig_type, area_ratio=ar,
                    page_no=page_no,
                )
                if ocr_result is None:
                    continue

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

    def _append_ocr_result(
        self,
        content: PageContent,
        ocr_result: dict,
        bbox: list[float],
        page_no: int,
    ) -> None:
        """OCR 결과를 fig_type에 따라 content.images / tables / charts에 추가합니다."""
        vl_fig_type = ocr_result.get("vl_fig_type")

        if vl_fig_type in ("table_image", "chart"):
            parsed = vl_parse(ocr_result["text"], vl_fig_type, page_no)
            if vl_fig_type == "table_image":
                content.tables.append(TableBlock(
                    data=[],
                    markdown=parsed["markdown"],
                    bbox=bbox,
                ))
            else:
                content.charts.append(ChartBlock(
                    bbox=bbox,
                    description=parsed["raw_text"],
                    extracted_data={
                        "title": parsed.get("title", ""),
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
    ) -> dict | None:
        """Paddle(+Surya) OCR을 실행하고 결과 dict를 반환합니다.

        품질 필터에 걸리거나 텍스트가 없으면 None 반환.
        결과 dict에 quality_score와 (debug_ocr=True 시) debug 정보가 포함됩니다.
        """
        image = preprocess_for_ocr(image, upscale=self.ocr_upscale)

        paddle_lines = self._paddle.run(image)  # type: ignore[union-attr]
        paddle_quality = self._ocr_quality(paddle_lines)

        print(f"    [OCR{tag}] Paddle only (quality={paddle_quality:.2f})")
        result = voter.vote(paddle_lines, threshold=0.0)
        result["sources"] = ["paddle_only"]
        result["paddle_lines"] = paddle_lines
        self._ocr_stats.paddle_only_count += 1
        if fig_type in ("diagram", "chart"):
            self._ocr_stats.chart_paddle_only_count += 1
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

        paddle_char_count = sum(len(l) for l in paddle_lines)
        voted_char_count  = len(voted_text.replace("\n", ""))

        paddle_line_count = len(paddle_lines)
        voted_line_count  = len([l for l in voted_text.split("\n") if l.strip()])

        self._ocr_stats.accumulate_char_counts(
            paddle_chars=paddle_char_count,
            voted_chars=voted_char_count,
        )

        # ── debug 정보 수집 (debug_ocr=True 일 때만) ─────────────────────────
        if self.debug_ocr:
            result["debug"] = {
                "paddle_raw":        paddle_lines,
                "voted_text":        voted_text,
                "paddle_quality":    round(paddle_quality, 3),
                "voting_path":       voting_path,
                "filter_reason":     result.get("filter_reason"),
                "quality_score":     q_score,
                "fig_type":          fig_type,
                "area_ratio":        round(area_ratio, 4),
                "image_width":       image.width,
                "image_height":      image.height,
                "image_area":        image.width * image.height,
                "paddle_char_count": paddle_char_count,
                "voted_char_count":  voted_char_count,
                "paddle_line_count": paddle_line_count,
                "voted_line_count":  voted_line_count,
            }

            entry = {
                "page":          page_no,
                "fig_type":      fig_type,
                "quality_score": q_score,
                "paddle_raw":    "\n".join(paddle_lines),
                "voted_text":    voted_text,
                "final_text":    None,
            }
            self._worst_ocr.append(entry)
            # quality_score 오름차순으로 상위 20개만 유지
            self._worst_ocr.sort(key=lambda x: x["quality_score"])
            if len(self._worst_ocr) > 20:
                self._worst_ocr = self._worst_ocr[:20]

        return result
