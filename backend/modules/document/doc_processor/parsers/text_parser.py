from __future__ import annotations

import fitz

from doc_processor.core.models import TextBlock

# 폰트 크기 기준으로 스타일 분류
_STYLE_THRESHOLDS = [
    (20.0, "title"),
    (14.0, "heading"),
    (9.0, "body"),
]


def _infer_style(size: float) -> str:
    for threshold, style in _STYLE_THRESHOLDS:
        if size >= threshold:
            return style
    return "caption"


def _join_spans(spans: list[dict]) -> str:
    """같은 줄의 span들을 이어붙인다.

    PyMuPDF는 폰트가 바뀌는 지점마다(실제 글자 간격이 0이거나 겹쳐도) span을
    나누는 경우가 있어서, 무조건 공백으로 합치면 없던 공백이 생긴다
    (예: 특정 글자만 다른 서브셋 폰트로 렌더링된 정부 문서). span 사이 실제
    x좌표 간격이 양수(> 0)일 때만 공백을 넣고, 0 이하(맞닿음/겹침)면 그대로 붙인다.
    """
    parts: list[str] = []
    prev_x1: float | None = None
    for s in spans:
        t = s.get("text", "").strip()
        if not t:
            continue
        sb = s.get("bbox")
        if prev_x1 is not None and sb and sb[0] - prev_x1 > 0:
            parts.append(" ")
        parts.append(t)
        if sb:
            prev_x1 = sb[2]
    return "".join(parts)


def extract_text_blocks(fitz_page: fitz.Page) -> list[TextBlock]:
    """PyMuPDF로 텍스트 블록을 추출합니다. 폰트/스타일 정보 포함.

    span 단위가 아닌 line 단위로 병합합니다.
    같은 줄(line) 안의 여러 span은 공백으로 합쳐 하나의 TextBlock으로 만듭니다.
    이렇게 해야 '날짜별로\\n아침\\n점심' 처럼 단어마다 줄바꿈되는 현상을 방지합니다.

    대표 span 선택 기준: 가장 긴 텍스트를 가진 span (폰트·크기 기준)
    """
    blocks: list[TextBlock] = []
    raw = fitz_page.get_text("dict")

    for block in raw.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block
            continue

        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue

            line_text = _join_spans(spans)
            if not line_text:
                continue

            # 대표 span: 텍스트가 가장 긴 span 기준으로 폰트/크기/bbox 결정
            rep_span = max(spans, key=lambda s: len(s.get("text", "")))
            font  = rep_span.get("font", "")
            size  = float(rep_span.get("size", 0.0))
            # line 전체를 감싸는 bbox: 첫 span x0 ~ 마지막 span x1, y는 line wdir 기준
            sb = [s["bbox"] for s in spans if "bbox" in s]
            x0 = min(b[0] for b in sb) if sb else 0.0
            y0 = min(b[1] for b in sb) if sb else 0.0
            x1 = max(b[2] for b in sb) if sb else 0.0
            y1 = max(b[3] for b in sb) if sb else 0.0
            bbox  = [x0, y0, x1, y1]
            style = _infer_style(size)

            blocks.append(TextBlock(
                text=line_text,
                bbox=bbox,
                font=font,
                size=size,
                style=style,
            ))

    return blocks
