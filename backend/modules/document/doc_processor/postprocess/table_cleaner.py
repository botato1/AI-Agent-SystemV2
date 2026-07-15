from __future__ import annotations

import re
from typing import Any

from doc_processor.core.models import TableBlock
from doc_processor.parsers.table_parser import _to_markdown


def _normalize_header(cell: Any) -> str:
    """헤더 셀 텍스트를 정규화합니다."""
    if cell is None:
        return ""
    text = str(cell).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _fill_missing_cells(rows: list[list[Any]]) -> list[list[Any]]:
    """모든 행의 열 수를 최대값으로 맞춥니다 (빈 칸으로 채움)."""
    if not rows:
        return rows
    max_cols = max(len(row) for row in rows)
    return [row + [None] * (max_cols - len(row)) for row in rows]


def _remove_all_empty_rows(rows: list[list[Any]]) -> list[list[Any]]:
    """모든 셀이 비어있는 행을 제거합니다."""
    return [
        row for row in rows
        if any(c is not None and str(c).strip() for c in row)
    ]


def clean_tables(tables: list[TableBlock]) -> list[TableBlock]:
    """표 블록 리스트를 정제합니다."""
    cleaned: list[TableBlock] = []
    for table in tables:
        rows = table.data

        # 1. 빈 행 제거
        rows = _remove_all_empty_rows(rows)
        if not rows:
            continue

        # 2. 열 수 통일
        rows = _fill_missing_cells(rows)

        # 3. 헤더 정규화 (첫 행)
        rows[0] = [_normalize_header(c) for c in rows[0]]

        # 4. Markdown 재생성
        markdown = _to_markdown(rows)

        cleaned.append(TableBlock(
            data=rows,
            markdown=markdown,
            bbox=table.bbox,
        ))
    return cleaned
