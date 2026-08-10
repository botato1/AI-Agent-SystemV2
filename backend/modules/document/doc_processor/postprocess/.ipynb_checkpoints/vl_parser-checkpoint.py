"""Qwen3-VL 출력 파서.

VLEngine.run()이 반환하는 raw 텍스트를 정제하고 구조화합니다.

반환 구조:
    table_image → {"type": "table", "page": N, "markdown": "...", "raw_text": "..."}
    chart       → {"type": "chart", "page": N, "raw_text": "...", "data": [...], "title": ""}
"""
from __future__ import annotations

import re

# Qwen3-VL 서두 패턴 (한국어/영어 공통)
_PREAMBLE_RE = re.compile(
    r'^(?:'
    r'물론입니다[.,!]?\s*'
    r'|네[.,!]?\s*'
    r'|Sure[.,!]?\s*'
    r'|Of course[.,!]?\s*'
    r'|Here(?:\'s| is) .*?[.]\s*'
    r'|아래[는은]\s+.*?[.]\s*'
    r'|다음[은는]\s+.*?[.]\s*'
    r')',
    re.IGNORECASE | re.DOTALL,
)

# 구분선 행 (|---|---| 형태) — 하이픈/콜론만으로 구성된 셀
_SEP_ROW_RE = re.compile(r'^\s*\|(?:[\s\-:]+\|)+\s*$')

# 마크다운 헤딩
_HEADING_RE = re.compile(r'^#{1,6}\s+(.+)$')


def _strip_preamble(text: str) -> str:
    """Qwen3-VL 서두 문장을 반복 제거합니다."""
    text = text.strip()
    for _ in range(5):
        new = _PREAMBLE_RE.sub("", text, count=1).strip()
        new = re.sub(r'^-{3,}\s*', '', new).strip()
        if new == text:
            break
        text = new
    return text


def _extract_title(text: str) -> str:
    """첫 번째 마크다운 헤딩을 제목으로 추출합니다."""
    for line in text.split("\n"):
        m = _HEADING_RE.match(line.strip())
        if m:
            return m.group(1).strip()
    return ""


def _split_pipe_tables(text: str) -> list[list[list[str]]]:
    """마크다운 텍스트에서 파이프 테이블들을 표 단위로 분리해 추출합니다.

    파이프가 없는 줄(제목·빈 줄 등)이 나오면 현재 표를 끝내고 새 표를
    시작합니다. 과거에는 모든 파이프 행을 하나로 합쳐서, VL이 표 2개를
    연속으로 출력하면 두 번째 표의 데이터가 첫 표의 헤더(컬럼명)에
    잘못 매핑되는 버그가 있었음.

    구분선 행(|---|---|)은 스킵합니다.
    반환: 표 목록. 각 표는 행 목록(첫 행 = 헤더), 행이 2개 미만인 표는 제외.
    """
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.split("\n"):
        s = line.strip()
        if s and "|" in s:
            if _SEP_ROW_RE.match(s):
                continue
            cells = [c.strip() for c in s.strip(" |").split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 2:
                current.append(cells)
                continue
        # 파이프 행이 아님 → 현재 표 종료
        if current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return [t for t in tables if len(t) >= 2]


def _try_numeric(val: str) -> int | float | str:
    """셀 값을 숫자로 변환 시도. 실패 시 원본 문자열 반환."""
    v = re.sub(r'[,억조원%\s**()\[\]]', '', val).strip()
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return val


def _rows_to_data(rows: list[list[str]]) -> list[dict]:
    """헤더 행을 키로 사용해 데이터 행을 dict 리스트로 반환합니다."""
    if len(rows) < 2:
        return []
    headers = rows[0]
    return [
        {headers[i] if i < len(headers) else f"col{i}": _try_numeric(cell) for i, cell in enumerate(row)}
        for row in rows[1:]
    ]


def _fcel_to_markdown(text: str) -> str:
    """PaddleOCR-VL <fcel>/<nl> 포맷을 마크다운 표로 변환합니다."""
    if "<fcel>" not in text:
        return text
    rows = []
    for line in text.strip().split("<nl>"):
        line = line.strip()
        if not line:
            continue
        cells = [c.strip() for c in line.split("<fcel>") if c.strip()]
        if cells:
            rows.append(cells)
    if not rows:
        return text
    md = "| " + " | ".join(rows[0]) + " |\n"
    md += "| " + " | ".join(["---"] * len(rows[0])) + " |\n"
    for row in rows[1:]:
        md += "| " + " | ".join(row) + " |\n"
    return md.strip()


# Paddle-VL 병합 셀 태그 — 마크다운 변환 후 제거
_PADDLE_CELL_TAG_RE = re.compile(r'<(?:lcel|ecel|ucel)>')


def _clean_paddle_tags(text: str) -> str:
    """Paddle-VL 병합 셀 태그(<lcel>/<ecel>/<ucel>)를 제거합니다."""
    return _PADDLE_CELL_TAG_RE.sub("", text).strip()


def parse(raw_text: str, fig_type: str, page_no: int) -> dict:
    """Qwen3-VL raw 텍스트를 정제하고 구조화합니다.

    Args:
        raw_text: VLEngine.run()이 반환한 텍스트
        fig_type: "table_image" | "chart"
        page_no:  1-based 페이지 번호

    Returns:
        table_image: {"type": "table", "page": N, "markdown": str, "raw_text": str}
        chart:       {"type": "chart", "page": N, "raw_text": str,
                      "data": list[dict], "title": str}
    """
    cleaned = _strip_preamble(raw_text)

    if fig_type == "table_image":
        markdown = _fcel_to_markdown(cleaned)
        markdown = _clean_paddle_tags(markdown)
        return {
            "type":     "table",
            "page":     page_no,
            "markdown": markdown,
            "raw_text": cleaned,
        }

    if fig_type == "diagram":
        return {
            "type":     "diagram",
            "page":     page_no,
            "raw_text": cleaned,
        }

    # chart — 표가 여러 개면 각 표의 헤더로 독립 변환 후 합침
    title = _extract_title(cleaned)
    data: list[dict] = []
    for rows in _split_pipe_tables(cleaned):
        data.extend(_rows_to_data(rows))

    return {
        "type":     "chart",
        "page":     page_no,
        "title":    title,
        "raw_text": cleaned,
        "data":     data,
    }