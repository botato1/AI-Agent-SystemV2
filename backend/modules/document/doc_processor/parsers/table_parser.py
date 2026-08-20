from __future__ import annotations

from typing import Any

import pdfplumber

from doc_processor.core.models import TableBlock


def _to_markdown(table: list[list[Any]]) -> str:
    """2D 배열을 Markdown Table 문자열로 변환합니다."""
    if not table:
        return ""

    def cell(v: Any) -> str:
        return str(v).replace("\n", " ").replace("|", "\\|") if v is not None else ""

    rows = [[cell(c) for c in row] for row in table]
    col_count = max(len(r) for r in rows)

    # 열 수 통일
    rows = [r + [""] * (col_count - len(r)) for r in rows]

    header = "| " + " | ".join(rows[0]) + " |"
    separator = "| " + " | ".join(["---"] * col_count) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])

    parts = [header, separator]
    if body:
        parts.append(body)
    return "\n".join(parts)


def _is_header_footer(bbox: tuple, page_height: float, margin: float = 0.10) -> bool:
    """페이지 상단/하단 margin 영역에 있으면 헤더/푸터로 판단합니다."""
    _, top, _, bottom = bbox
    return bottom < page_height * margin or top > page_height * (1 - margin)


def _has_real_content(data: list[list]) -> bool:
    """실제 내용이 있는 셀이 2개 이상인지 확인합니다."""
    non_empty = sum(
        1 for row in data for cell in row
        if cell is not None and str(cell).strip()
    )
    return non_empty >= 2


def _content_fill_ratio(data: list[list]) -> float:
    """전체 셀 대비 실제 값이 있는 셀의 비율을 계산합니다."""
    total = sum(len(row) for row in data)
    if total == 0:
        return 0.0
    filled = sum(
        1 for row in data for cell in row
        if cell is not None and str(cell).strip()
    )
    return filled / total


# 배지/리본 같은 장식 이미지나 정렬된 문단 텍스트를, pdfplumber가 표 경계선으로
# 착각해서 대부분 빈 셀인 표를 잘못 감지하는 경우가 있다. 채워진 셀 비율이
# 이 값보다 낮으면 진짜 표가 아니라 그런 오탐으로 보고 제외한다.
MIN_FILL_RATIO = 0.6


def extract_tables(plumber_page: pdfplumber.page.Page) -> list[TableBlock]:
    """pdfplumber로 표를 추출하고 Markdown Table을 생성합니다."""
    results: list[TableBlock] = []
    page_height = plumber_page.height

    for table in plumber_page.find_tables():
        data = table.extract() or []
        if not data:
            continue

        if _is_header_footer(table.bbox, page_height):
            continue

        if not _has_real_content(data):
            continue

        if _content_fill_ratio(data) < MIN_FILL_RATIO:
            continue

        bbox = list(table.bbox)
        markdown = _to_markdown(data)

        results.append(TableBlock(
            data=data,
            markdown=markdown,
            bbox=bbox,
        ))

    return results