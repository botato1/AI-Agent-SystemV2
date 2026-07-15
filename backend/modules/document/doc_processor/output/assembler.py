from __future__ import annotations

import hashlib
from pathlib import Path

from doc_processor.core.models import DocumentResult, PageResult
from doc_processor.schemas.document import DocumentSchema
from doc_processor.schemas.metadata import (
    DocumentMetadata,
    PageResultSchema,
)


# ── ID 생성 ──────────────────────────────────────────────────────────────────

def _doc_id(source: str) -> str:
    return "doc_" + hashlib.md5(source.encode()).hexdigest()[:12]


# ── content 조립 (plain text) ────────────────────────────────────────────────

def _build_plain_text(doc: DocumentResult) -> str:
    """PyMuPDF 텍스트 + OCR 텍스트 + 표 텍스트를 모두 합쳐 반환합니다."""
    parts: list[str] = []
    for page in doc.pages:
        seen: set[str] = set()  # 페이지 내 완전 중복 제거

        # 텍스트 블록
        for block in page.content.text:
            key = block.text.strip()
            if key and key not in seen:
                seen.add(key)
                parts.append(key)
        # 표 — pdfplumber 추출분 (data) + VL 추출분 (markdown)
        for table in page.content.tables:
            if table.data:
                for row in table.data:
                    row_text = " ".join(str(c) for c in row if c is not None)
                    if row_text.strip() and row_text.strip() not in seen:
                        seen.add(row_text.strip())
                        parts.append(row_text.strip())
            elif table.markdown.strip():
                key = table.markdown.strip()
                if key not in seen:
                    seen.add(key)
                    parts.append(key)
        # 이미지 OCR (VL 결과는 이제 tables/charts로 분리됨)
        for img in page.content.images:
            key = img.ocr_text.strip()
            if key and key not in seen:
                seen.add(key)
                parts.append(key)
        # 차트 (VL 결과 — RAG 검색용으로 포함)
        for chart in page.content.charts:
            key = chart.description.strip()
            if key and key not in seen:
                seen.add(key)
                parts.append(key)
    return "\n".join(parts)


# ── content_markdown 조립 ────────────────────────────────────────────────────

def _build_chunks(doc: DocumentResult) -> list[dict]:
    """전체 텍스트 청크 수집 (caption 제외, title/body만)."""
    chunks: list[dict] = []
    for page in doc.pages:
        for block in page.content.text:
            # caption 제외
            if block.style == "caption":
                continue
            # title/body만 포함
            if block.style in ("title", "body"):
                chunks.append({
                    "text": block.text,
                    "page_number": page.page,
                    "style": block.style,
                    "font": block.font,
                    "size": round(block.size, 2) if block.size else None,
                })
    return chunks


# ── 태그 자동 생성 ────────────────────────────────────────────────────────────

def _build_tables(doc: DocumentResult) -> list[dict]:
    """VL가 추출한 표를 전체 문서 단위로 수집합니다."""
    tables: list[dict] = []
    for page in doc.pages:
        for table in page.content.tables:
            if not table.data and table.markdown.strip():  # VL 분
                tables.append({
                    "page": page.page,
                    "markdown": table.markdown.strip(),
                })
    return tables


def _build_charts(doc: DocumentResult) -> list[dict]:
    """VL가 추출한 차트를 전체 문서 단위로 수집합니다."""
    charts: list[dict] = []
    for page in doc.pages:
        for chart in page.content.charts:
            entry: dict = {
                "page": page.page,
                "raw_text": chart.description.strip(),
            }
            if chart.extracted_data:
                if chart.extracted_data.get("title"):
                    entry["title"] = chart.extracted_data["title"]
                if chart.extracted_data.get("data"):
                    entry["data"] = chart.extracted_data["data"]
            charts.append(entry)
    return charts


def _auto_tags(doc: DocumentResult) -> list[str]:
    tags = ["pdf", doc.pdf_type]
    if any(page.content.tables for page in doc.pages):
        tags.append("table")
    if any(page.content.images for page in doc.pages):
        tags.append("image")
    if any(page.fallback_used for page in doc.pages):
        tags.append("gemini-fallback")
    return tags


# ── 엔진 목록 수집 ────────────────────────────────────────────────────────────

def _collect_engines(doc: DocumentResult) -> list[str]:
    engines = ["pymupdf", "pdfplumber"]
    has_ocr = any(page.content.images for page in doc.pages)
    if has_ocr:
        engines += ["paddle"]
    if any(page.fallback_used for page in doc.pages):
        engines.append("gemini")
    return engines


# ── 문서 평균 confidence ─────────────────────────────────────────────────────

def _avg_confidence(doc: DocumentResult) -> float:
    scores: list[float] = []
    for page in doc.pages:
        d = page.confidence.to_dict()
        # overall·chart는 제외하고 실제 추출 항목만 평균
        scores.extend(v for k, v in d.items() if k not in ("overall", "chart"))
    if not scores:
        return 1.0
    return round(sum(scores) / len(scores), 3)


# ── status 결정 ───────────────────────────────────────────────────────────────

def _status(doc: DocumentResult, avg_conf: float) -> str:
    if not doc.pages:
        return "error"
    if avg_conf < 0.7:
        return "uploaded"   # 신뢰도 낮음 — 사람 검토 필요
    return "processed"



# ── page_results 조립 (디버깅용) ─────────────────────────────────────────────

def _build_page_results(doc: DocumentResult) -> list[PageResultSchema]:
    results: list[PageResultSchema] = []
    for page in doc.pages:
        pg = page.page_number if hasattr(page, "page_number") else page.page
        results.append(PageResultSchema(
            page_number=pg,
            text_blocks=[
                {"text": b.text, "style": b.style, "font": b.font, "size": round(b.size, 2)}
                for b in page.content.text
            ],
            tables=[
                {"markdown": t.markdown, "rows": len(t.data)}
                for t in page.content.tables
            ],
            images=[
                {
                    "bbox": img.bbox,
                    "ocr_text": img.ocr_text,
                    "voting_confidence": img.voting_confidence,
                    "quality_score": img.quality_score if img.quality_score >= 0 else None,
                    **({"debug": img.debug} if img.debug is not None else {}),
                }
                for img in page.content.images
            ],
            charts=[
                {"description": c.description[:100]}
                for c in page.content.charts
            ],
            confidence=page.confidence.to_dict(),
            fallback_used=page.fallback_used,
        ))
    return results


# ── 최종 조립 ─────────────────────────────────────────────────────────────────

def _is_fallback_candidate(doc: DocumentResult, avg_conf: float) -> bool:
    """Gemini 보정이 권장되는 문서인지 판단.

    조건:
    - 문서 평균 confidence < 0.70
    - 또는 이미지 confidence 평균 < 0.50 (OCR 품질이 낮은 이미지 포함)
    """
    if avg_conf < 0.70:
        return True
    image_scores = [p.confidence.image for p in doc.pages if p.content.images]
    if image_scores and (sum(image_scores) / len(image_scores)) < 0.50:
        return True
    return False


def assemble(doc: DocumentResult) -> DocumentSchema:
    """DocumentResult → DocumentSchema 변환의 단일 진입점."""
    doc_id = _doc_id(doc.source)
    avg_conf = _avg_confidence(doc)
    fallback_candidate = _is_fallback_candidate(doc, avg_conf)

    if fallback_candidate:
        print(f"[Assembler] fallback_candidate=True (avg_conf={avg_conf:.3f})")

    return DocumentSchema(
        id=doc_id,
        title=Path(doc.source).stem,
        source="pdf",
        content=_build_plain_text(doc),
        tables=_build_tables(doc),
        charts=_build_charts(doc),
        chunks=_build_chunks(doc),
        tags=_auto_tags(doc),
        status=_status(doc, avg_conf),
        page_results=_build_page_results(doc),
        metadata=DocumentMetadata(
            confidence_score=avg_conf,
            engines=_collect_engines(doc),
            fallback_used=any(p.fallback_used for p in doc.pages),
            page_count=max(len(doc.pages), 1),
            file_path=doc.source,
            pdf_type=doc.pdf_type,
            fallback_candidate=fallback_candidate,
            ocr_attempt_count=doc.ocr_stats.attempt_count,
            ocr_skip_count=doc.ocr_stats.skip_count,
            ocr_success_count=doc.ocr_stats.success_count,
            ocr_empty_count=doc.ocr_stats.empty_count,
            ocr_filtered_count=doc.ocr_stats.filtered_count,
            ocr_useful_count=doc.ocr_stats.useful_count,
            ocr_garbage_count=doc.ocr_stats.garbage_count,
            ocr_avg_quality_score=doc.ocr_stats.avg_quality_score,
            ocr_skip_ratio=doc.ocr_stats.skip_ratio,
            ocr_success_ratio=doc.ocr_stats.success_ratio,
            ocr_useful_ratio=doc.ocr_stats.useful_ratio,
            ocr_paddle_only_count=doc.ocr_stats.paddle_only_count,
            ocr_chart_paddle_only_count=doc.ocr_stats.chart_paddle_only_count,
            ocr_table_tsr_count=doc.ocr_stats.table_tsr_count,
            processing_time_sec=doc.ocr_stats.processing_time_sec,
            pages_per_second=round(
                len(doc.pages) / doc.ocr_stats.processing_time_sec, 3
            ) if doc.ocr_stats.processing_time_sec > 0 else 0.0,
        ),
    )
