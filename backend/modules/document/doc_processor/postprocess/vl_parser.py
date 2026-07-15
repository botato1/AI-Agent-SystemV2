"""VL(PaddleOCR-VL) 출력 파서.

VLEngine.run()이 반환하는 raw 텍스트를 정제하고 구조화합니다.

raw 텍스트 형태:
    "User: Table Recognition:\nAssistant: | col | ... |"
    "User: Chart Recognition:\nAssistant: Year | Value\n2023 | 53"

반환 구조:
    table_image → {"type": "table", "page": N, "markdown": "...", "raw_text": "..."}
    chart       → {"type": "chart", "page": N, "raw_text": "...", "data": [...], "title": ""}
"""
from __future__ import annotations

import re


# VL 프롬프트 prefix 패턴
_PREFIX_RE = re.compile(
    r'^(?:User:\s*(?:Table|Chart)\s+Recognition:.*?\n)?'
    r'(?:Assistant:\s*)?',
    re.IGNORECASE | re.DOTALL,
)

# 파이프 테이블 행 패턴
_PIPE_ROW_RE = re.compile(r'^\s*\|.*\|\s*$')
# 구분선 행 (|---|---|)
_SEP_ROW_RE = re.compile(r'^\s*\|[\s\-:]+\|\s*$')


def _strip_prefix(text: str) -> str:
    """'User: ...Recognition:\nAssistant:' prefix를 제거합니다."""
    # "assistant" 경계로 분리 (대소문자 무관)
    lower = text.lower()
    idx = lower.rfind("assistant")
    if idx != -1:
        after = text[idx + len("assistant"):].lstrip(": \n")
        if after.strip():
            return after.strip()
    # prefix 패턴으로 시도
    cleaned = _PREFIX_RE.sub("", text, count=1).strip()
    return cleaned if cleaned else text.strip()


def _parse_pipe_table(text: str) -> list[list[str]] | None:
    """파이프 테이블 또는 파이프 구분 텍스트에서 데이터를 추출합니다.

    지원 형식:
      1. 완전한 마크다운 테이블: | col | col |
      2. 파이프 구분 (앞뒤 | 없음): col | col

    Returns:
        행별 셀 리스트. 파싱 불가 시 None.
    """
    lines = [l for l in text.split("\n") if l.strip()]
    rows: list[list[str]] = []
    for line in lines:
        if _SEP_ROW_RE.match(line):
            continue  # 구분선 스킵
        if "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            cells = [c for c in cells if c]  # 빈 셀 제거
            if len(cells) >= 2:
                rows.append(cells)
    return rows if len(rows) >= 2 else None


def _try_numeric(val: str) -> int | float | str:
    """셀 값을 숫자로 변환 시도. 실패 시 원본 문자열 반환."""
    v = val.replace(",", "").replace("%", "").strip()
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return val


def _rows_to_data(rows: list[list[str]]) -> list[list]:
    """헤더 제외 후 숫자 변환된 데이터 행 반환."""
    if not rows:
        return []
    data_rows = rows[1:] if len(rows) > 1 else rows
    return [[_try_numeric(c) for c in row] for row in data_rows]


def parse(raw_text: str, fig_type: str, page_no: int) -> dict:
    """VL raw 텍스트를 정제하고 구조화합니다.

    Args:
        raw_text: VLEngine.run()이 반환한 텍스트
        fig_type: "table_image" | "chart"
        page_no:  1-based 페이지 번호

    Returns:
        table_image: {"type": "table", "page": N, "markdown": str, "raw_text": str}
        chart:       {"type": "chart", "page": N, "raw_text": str,
                      "data": list, "title": str}
    """
    cleaned = _strip_prefix(raw_text)

    if fig_type == "table_image":
        return {
            "type": "table",
            "page": page_no,
            "markdown": cleaned,
            "raw_text": cleaned,
        }

    # chart
    rows = _parse_pipe_table(cleaned)
    if rows:
        data = _rows_to_data(rows)
        title = ""
    else:
        data = []
        title = ""

    return {
        "type": "chart",
        "page": page_no,
        "title": title,
        "raw_text": cleaned,
        "data": data,
    }
