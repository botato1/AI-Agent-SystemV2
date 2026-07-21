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

        bbox = list(table.bbox)
        markdown = _to_markdown(data)

        results.append(TableBlock(
            data=data,
            markdown=markdown,
            bbox=bbox,
        ))

    return results