from __future__ import annotations

from doc_processor.core.models import TableBlock

# ── 가중치 ────────────────────────────────────────────────────────────────────
_W_HEADER       = 0.25   # 헤더 존재 여부
_W_NULL         = 0.25   # 빈 셀 비율
_W_CONSISTENCY  = 0.20   # 행별 열 수 일관성
_W_SIZE         = 0.20   # 표 크기 (너무 작으면 감점)
_W_CONTENT      = 0.10   # 셀 내용 품질 (숫자/텍스트 혼재 여부)


def _header_score(rows: list[list]) -> float:
    """첫 행이 헤더 역할을 하는지 평가.

    - 첫 행 셀이 모두 채워져 있고
    - 두 번째 행과 내용이 다르면 헤더로 판정
    """
    if not rows or not rows[0]:
        return 0.0

    first_row = [str(c).strip() for c in rows[0] if c is not None]
    filled_ratio = len([c for c in first_row if c]) / max(len(rows[0]), 1)

    if len(rows) < 2:
        return filled_ratio * 0.7  # 행이 1개면 헤더 판정 불확실

    second_row = [str(c).strip() for c in rows[1] if c is not None]
    different = first_row != second_row
    return filled_ratio * (1.0 if different else 0.5)


def _null_score(rows: list[list]) -> float:
    """빈 셀이 적을수록 높은 점수."""
    total = sum(len(row) for row in rows)
    if total == 0:
        return 0.0
    null_count = sum(
        1 for row in rows
        for c in row
        if c is None or str(c).strip() == ""
    )
    return 1.0 - (null_count / total)


def _consistency_score(rows: list[list]) -> float:
    """모든 행의 열 수가 일치할수록 높은 점수."""
    if not rows:
        return 0.0
    col_counts = [len(row) for row in rows]
    most_common = max(set(col_counts), key=col_counts.count)
    consistent = sum(1 for c in col_counts if c == most_common)
    return consistent / len(col_counts)


def _size_score(rows: list[list]) -> float:
    """행/열 수가 적절할수록 높은 점수.

    - 2행 2열 이상이면 기본 점수
    - 10행 이상이면 만점
    """
    if not rows:
        return 0.0
    row_count = len(rows)
    col_count = max(len(r) for r in rows) if rows else 0

    row_score = min(row_count / 10.0, 1.0)
    col_score = min(col_count / 4.0, 1.0)
    return (row_score + col_score) / 2.0


def _content_score(rows: list[list]) -> float:
    """셀 내용이 다양(텍스트+숫자 혼재)할수록 구조가 명확한 표."""
    cells = [str(c).strip() for row in rows for c in row if c is not None and str(c).strip()]
    if not cells:
        return 0.0
    has_text = any(not c.replace(".", "").replace(",", "").isdigit() for c in cells)
    has_number = any(c.replace(".", "").replace(",", "").isdigit() for c in cells)
    return 1.0 if (has_text and has_number) else 0.7


def score(tables: list[TableBlock]) -> float:
    """TableBlock 리스트의 품질 추정 점수를 반환합니다 (0.0 ~ 1.0).

    표가 없으면 1.0 (해당 없음).
    """
    if not tables:
        return 1.0

    table_scores: list[float] = []
    for table in tables:
        rows = table.data
        if not rows:
            table_scores.append(0.0)
            continue

        h = _header_score(rows)
        n = _null_score(rows)
        c = _consistency_score(rows)
        s = _size_score(rows)
        q = _content_score(rows)

        table_scores.append(
            h * _W_HEADER +
            n * _W_NULL +
            c * _W_CONSISTENCY +
            s * _W_SIZE +
            q * _W_CONTENT
        )

    return round(sum(table_scores) / len(table_scores), 3)
