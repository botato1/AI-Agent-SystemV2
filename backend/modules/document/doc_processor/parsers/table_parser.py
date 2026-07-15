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


def extract_tables(plumber_page: pdfplumber.page.Page) -> list[TableBlock]:
    """pdfplumber로 표를 추출하고 Markdown Table을 생성합니다."""
    results: list[TableBlock] = []

    for table in plumber_page.find_tables():
        data = table.extract() or []
        if not data:
            continue

        bbox = list(table.bbox)  # (x0, top, x1, bottom)
        markdown = _to_markdown(data)

        results.append(TableBlock(
            data=data,
            markdown=markdown,
            bbox=bbox,
        ))

    return results
