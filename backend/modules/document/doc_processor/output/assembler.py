from __future__ import annotations

import hashlib
import re
from pathlib import Path

from doc_processor.core.models import DocumentResult
from doc_processor.schemas.document import DocumentSchema
from doc_processor.schemas.metadata import DocumentMetadata


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
        # 셀을 " | "로 구분해서 넣어야 프론트가 파이프 개수로 표를 감지해 렌더링할 수 있다.
        for table in page.content.tables:
            if table.data:
                for row in table.data:
                    t = " | ".join(str(c) for c in row if c is not None).strip()
                    if t and t not in seen:
                        seen.add(t)
                        parts.append(t)
            else:
                key = table.markdown.strip()
                if key and key not in seen:
                    seen.add(key)
                    parts.append(key)
        # 이미지 OCR (VL 결과는 이제 tables/charts로 분리됨)
        for img in page.content.images:
            key = img.ocr_text.strip()
            if key and key not in seen:
                seen.add(key)
                parts.append(key)
        # 차트 (VL 결과 — RAG 검색용으로 포함)
        # charts 배열과 동일한 필터 적용 — 필터에서 걸러진 환각/가비지
        # 텍스트가 content(검색 본문)에만 남는 오염 방지.
        # 제목 유효성은 더 이상 게이트가 아님 — 실제 데이터가 있으면
        # 제목을 못 찾아도 유실시키지 않는다 (_chart_effective_title 참고).
        for chart in page.content.charts:
            if not _chart_has_content(chart):
                continue
            # 수치가 신뢰할 수 없으면(환각) 가짜 표 대신 제목 + 페이지 번호만
            # 남기고, 실제 그림은 image_path로 저장된 크롭 이미지를 참고하게
            # 한다. 뒤에 오는 문단과 헷갈리지 않도록 빈 줄로 한 번 띄운다.
            data_reliable = _chart_data_reliable(chart)
            if data_reliable:
                key = chart.description.strip()
            else:
                title = _chart_effective_title(chart, page.page)
                key = f"[차트: {title}] (자동 인식 정확도가 낮아 원본 이미지 참고 · {page.page}페이지)"
            if key and key not in seen:
                seen.add(key)
                parts.append(key if data_reliable else key + "\n")
    return "\n".join(parts)


# ── 태그 자동 생성 ────────────────────────────────────────────────────────────

def _build_tables(doc: DocumentResult) -> list[dict]:
    """모든 표(pdfplumber + VL)를 전체 문서 단위로 수집합니다."""
    tables: list[dict] = []
    for page in doc.pages:
        for table in page.content.tables:
            if table.data:
                tables.append({
                    "page": page.page,
                    "data": table.data,
                    "markdown": table.markdown.strip(),
                    "image_path": table.image_path,
                })
            elif table.markdown.strip():
                tables.append({
                    "page": page.page,
                    "markdown": table.markdown.strip(),
                    "image_path": table.image_path,
                })
    return tables


_HAS_NUMBER_PAT = re.compile(r'\|\s*-?\d+\.?\d*\s*\|')


def _data_looks_hallucinated(data: list[dict]) -> bool:
    """VL이 같은 값을 기계적으로 반복 생성한 환각 데이터인지 검사합니다.

    숫자 셀이 8개 이상인데 유니크 값이 단 1개면 (예: 전 지역 -0.2)
    실제 차트를 읽지 못하고 지어낸 것으로 간주합니다.
    """
    nums = [
        v for row in data
        for v in row.values()
        if isinstance(v, (int, float))
    ]
    return len(nums) >= 8 and len(set(nums)) == 1


def _chart_series_values_identical(data: list[dict]) -> bool:
    """행마다 서로 다른 계열(컬럼)의 숫자 값이 전부 똑같은지 검사합니다.

    실제 서로 다른 지표(예: 부동산원 vs KB)가 매 시점 완전히 같은 값일 확률은
    거의 없다 — VL이 실제 곡선을 못 읽고 축 눈금(X/Y축 라벨)을 그대로
    값처럼 베낀 전형적인 환각 패턴이다. 행의 80% 이상에서 이 패턴이 나오면
    환각으로 간주한다.
    """
    numeric_rows = 0
    identical_rows = 0
    for row in data:
        nums = [v for v in row.values() if isinstance(v, (int, float))]
        if len(nums) >= 2:
            numeric_rows += 1
            if len(set(nums)) == 1:
                identical_rows += 1
    if numeric_rows == 0:
        return False
    return identical_rows / numeric_rows >= 0.8


def _chart_data_reliable(chart) -> bool:
    """차트의 data(계열 수치)를 표로 보여줄 만큼 신뢰할 수 있는지 확인합니다.

    신뢰할 수 없으면(환각으로 판단되면) 호출부에서 수치 표 대신 이미지로만
    보여주고, 텍스트는 제목 정도만 남긴다.
    """
    if not chart.extracted_data:
        return False
    data = chart.extracted_data.get("data")
    if not data:
        return False
    if _data_looks_hallucinated(data):
        return False
    if _chart_series_values_identical(data):
        return False
    return True


def _chart_has_content(chart) -> bool:
    """데이터나 의미 있는 텍스트가 있는 차트인지 확인합니다."""
    if chart.extracted_data and chart.extracted_data.get("data"):
        return not _data_looks_hallucinated(chart.extracted_data["data"])
    # 표 구조(|)도 없고 data도 없으면 섹션 구분 페이지 등 비차트 이미지
    if '|' not in chart.description:
        return False
    # 숫자 데이터가 없는 레이블 테이블 → 섹션 구분 페이지
    if not _HAS_NUMBER_PAT.search(chart.description):
        return False
    text = re.sub(r'[\s|#\-]', '', chart.description)
    return len(text) > 5


_NUM_PAT = re.compile(r'^-?\d+(\.\d+)?$')
_CITE_PREFIXES = ("자료", "출처", "주:", "주1", "※", "Source")
_UNIT_LABEL_PAT = re.compile(r'^\(.*\)$')  # 전체가 괄호로만 감싸진 텍스트 ("(% WoW)" 등 축 단위 라벨)

# 정보가 없는 제네릭 제목 — 정확 일치만 차단.
# startswith 필터는 "표준지 공시지가", "데이터센터 투자 현황" 같은
# 정상 제목까지 차단하므로 사용하지 않는다.
_GENERIC_TITLES = frozenset({
    "차트 데이터", "차트", "데이터", "데이터 표", "데이터 테이블",
    "그래프", "표", "인포그래픽",
})


def _title_is_valid(title: str) -> bool:
    """의미 있는 제목인지 확인합니다 (숫자·인용구·단순 단위 제외)."""
    if not title:
        return False
    t = title.strip()
    if _NUM_PAT.match(t):          # "-0.2", "4", "20" 등 순수 숫자
        return False
    if t.startswith(_CITE_PREFIXES):  # 출처 문구
        return False
    if _UNIT_LABEL_PAT.match(t):  # "(% WoW)", "(%)", "(pt)", "(단위: %)" 등 괄호로만 된 단위 표기
        return False
    if t in _GENERIC_TITLES:
        return False
    return True


_HALLUCINATION_REPEAT = 3  # 동일 행이 이 횟수 이상이면 VL 반복 환각으로 간주


def _dedupe_rows(data: list[dict]) -> list[dict]:
    """헤더가 데이터로 중복 삽입되거나 VL이 같은 행을 반복 생성한 경우 제거합니다.

    동일 행이 2번 나오는 것은 정상 데이터일 수 있어 유지하고,
    3번 이상 반복되는 행만 환각으로 보고 1개로 축소합니다.
    """
    from collections import Counter

    counts = Counter(str(row) for row in data)
    cleaned: list[dict] = []
    seen: set[str] = set()
    for row in data:
        # 헤더 행이 데이터로 섞여 들어온 경우 (첫 컬럼 값이 컬럼명과 동일)
        if row and next(iter(row.items()))[0] == next(iter(row.items()))[1]:
            continue
        key = str(row)
        if counts[key] >= _HALLUCINATION_REPEAT:
            if key in seen:
                continue
            seen.add(key)
        cleaned.append(row)
    return cleaned


def _extract_md_title(raw_text: str) -> str:
    """raw_text에서 첫 번째 ### 제목을 추출합니다."""
    for line in raw_text.splitlines():
        line = line.strip()
        if line.startswith("### "):
            return line[4:].strip()
    return ""


def _chart_title(chart) -> str:
    """차트의 유효한 제목을 반환합니다. 못 찾으면 ''.

    VL 제목 → raw_text의 ### 헤딩 순서로 시도합니다.
    charts 배열 포함 여부와 content(plain text) 포함 여부가
    같은 기준을 쓰도록 이 함수 하나로 판단합니다.
    """
    if not chart.extracted_data:
        return ""
    vl_title = chart.extracted_data.get("title", "")
    if _title_is_valid(vl_title):
        return vl_title
    md_title = _extract_md_title(chart.description or "")
    if _title_is_valid(md_title):
        return md_title
    return ""


def _chart_effective_title(chart, page_no: int) -> str:
    """진짜 제목을 못 찾아도 실제 데이터가 있는 차트를 통째로 버리지 않도록,
    축 단위 라벨 등 유효하지 않은 제목이라도 있으면 그거라도 쓰고,
    아예 없으면 페이지 번호 기반 제네릭 제목으로 대체합니다.
    """
    title = _chart_title(chart)
    if title:
        return title
    vl_title = (chart.extracted_data or {}).get("title", "").strip()
    if vl_title:
        return vl_title
    return f"차트 (페이지 {page_no})"


def _build_charts(doc: DocumentResult) -> list[dict]:
    """VL가 추출한 차트를 전체 문서 단위로 수집합니다."""
    charts: list[dict] = []
    for page in doc.pages:
        for chart in page.content.charts:
            if not _chart_has_content(chart):
                continue
            title = _chart_effective_title(chart, page.page)
            data_reliable = _chart_data_reliable(chart)
            entry: dict = {
                "page": page.page,
                "raw_text": chart.description.strip(),
                "title": title,
                "image_path": chart.image_path,
                # 프론트가 데이터 표 대신 이미지만 보여줘야 하는지 판단하는 플래그
                "data_reliable": data_reliable,
            }
            if data_reliable:
                entry["data"] = _dedupe_rows(chart.extracted_data["data"])
            charts.append(entry)
    return charts


def _build_diagrams(doc: DocumentResult) -> list[dict]:
    """VL가 추출한 다이어그램/인포그래픽을 전체 문서 단위로 수집합니다."""
    diagrams: list[dict] = []
    for page in doc.pages:
        for img in page.content.images:
            if getattr(img, "image_type", "image") != "diagram":
                continue
            raw_text = img.ocr_text.strip()
            if not raw_text:
                continue
            diagrams.append({
                "page": page.page,
                "raw_text": raw_text,
                "image_path": img.image_path,
            })
    return diagrams


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
    """실제로 사용된 엔진만 나열합니다 (통계·콘텐츠 기반)."""
    engines = ["pymupdf", "pdfplumber"]
    stats = doc.ocr_stats
    if stats.paddle_only_count or stats.paddle_surya_count:
        engines.append("paddle")
    if stats.paddle_surya_count:
        engines.append("surya")
    # VL 표 = data 없이 markdown만 있는 표 (PaddleOCR-VL 산출물)
    if any(
        (not t.data) and t.markdown.strip()
        for p in doc.pages for t in p.content.tables
    ):
        engines.append("paddle-vl")
    # 차트/다이어그램은 Qwen3-VL 산출물
    if any(
        p.content.charts
        or any(getattr(i, "image_type", "image") == "diagram" for i in p.content.images)
        for p in doc.pages
    ):
        engines.append("qwen3-vl")
    if any(p.fallback_used for p in doc.pages):
        engines.append("gemini")
    return engines


# ── 문서 평균 confidence ─────────────────────────────────────────────────────

def _avg_confidence(doc: DocumentResult) -> float:
    scores: list[float] = []
    for page in doc.pages:
        c = page.confidence
        # 해당 콘텐츠가 실제 존재하는 항목만 평균 — 없는 항목의
        # "해당 없음(1.0)" 기본값이 평균을 부풀리는 것 방지
        if page.content.text:
            scores.append(c.text)
        if page.content.tables:
            scores.append(c.table)
        if page.content.images:
            scores.append(c.image)
    if not scores:
        # 채점 가능한 콘텐츠가 전혀 없음 — 판단 불가이므로 중립값.
        # (1.0이면 무조건 통과, 0.0이면 무조건 검토로 쏠려서 중간값 사용)
        return 0.5
    return round(sum(scores) / len(scores), 3)


# ── status 결정 ───────────────────────────────────────────────────────────────

def _status(doc: DocumentResult, avg_conf: float) -> str:
    if not doc.pages:
        return "error"
    if avg_conf < 0.7:
        return "uploaded"   # 신뢰도 낮음 — 사람 검토 필요
    return "processed"



# ── chunks 조립 (청킹 담당자용) ──────────────────────────────────────────────

def _build_chunks(doc: DocumentResult) -> list[dict]:
    """텍스트 블록뿐 아니라 표/이미지 OCR/차트까지 _build_plain_text와 동일한
    소스로 채운다. 텍스트 블록만 넣으면 OCR/표/차트로만 존재하는 내용이
    chunks에서는 통째로 빠지고 content(원문 전체)에만 남는 유실이 발생했다.
    """
    chunks = []
    for page in doc.pages:
        pg = page.page

        for b in page.content.text:
            if b.style == "caption":
                continue
            chunks.append({
                "text": b.text,
                "style": b.style,
                "font": b.font,
                "size": round(b.size, 2),
                "page_number": pg,
            })

        for table in page.content.tables:
            if table.data:
                for row in table.data:
                    text = " | ".join(str(c) for c in row if c is not None).strip()
                    if text:
                        chunks.append({"text": text, "style": "table", "page_number": pg})
            elif table.markdown.strip():
                chunks.append({"text": table.markdown.strip(), "style": "table", "page_number": pg})

        for img in page.content.images:
            text = img.ocr_text.strip()
            if text:
                chunks.append({"text": text, "style": "image", "page_number": pg})

        for chart in page.content.charts:
            if not _chart_has_content(chart):
                continue
            if _chart_data_reliable(chart):
                text = chart.description.strip()
            else:
                title = _chart_effective_title(chart, pg)
                text = f"[차트: {title}] (자동 인식 정확도가 낮아 원본 이미지 참고)"
            if text:
                chunks.append({"text": text, "style": "chart", "page_number": pg})

    return chunks


# ── 최종 조립 ─────────────────────────────────────────────────────────────────

def assemble(doc: DocumentResult) -> DocumentSchema:
    """DocumentResult → DocumentSchema 변환의 단일 진입점."""
    doc_id = _doc_id(doc.source)
    avg_conf = _avg_confidence(doc)
    image_scores = [p.confidence.image for p in doc.pages if p.content.images]
    fallback_candidate = (
        avg_conf < 0.70
        or (bool(image_scores) and sum(image_scores) / len(image_scores) < 0.50)
    )

    if fallback_candidate:
        print(f"[Assembler] fallback_candidate=True (avg_conf={avg_conf:.3f})")

    return DocumentSchema(
        id=doc_id,
        title=Path(doc.source).stem,
        source="pdf",
        content=_build_plain_text(doc),
        tables=_build_tables(doc),
        charts=_build_charts(doc),
        diagrams=_build_diagrams(doc),
        chunks=_build_chunks(doc),
        tags=_auto_tags(doc),
        status=_status(doc, avg_conf),
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
            ocr_surya_ratio=doc.ocr_stats.surya_ratio,
            ocr_paddle_only_count=doc.ocr_stats.paddle_only_count,
            ocr_paddle_surya_count=doc.ocr_stats.paddle_surya_count,
            ocr_chart_paddle_only_count=doc.ocr_stats.chart_paddle_only_count,
            ocr_table_tsr_count=doc.ocr_stats.table_tsr_count,
            processing_time_sec=doc.ocr_stats.processing_time_sec,
            pages_per_second=round(
                len(doc.pages) / doc.ocr_stats.processing_time_sec, 3
            ) if doc.ocr_stats.processing_time_sec > 0 else 0.0,
        ),
    )