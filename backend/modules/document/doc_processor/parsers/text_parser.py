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

            # 같은 줄의 모든 span 텍스트를 공백으로 합침
            line_text = " ".join(
                s.get("text", "").strip()
                for s in spans
                if s.get("text", "").strip()
            )
            if not line_text:
                continue

            # 대표 span: 텍스트가 가장 긴 span 기준으로 폰트/크기/bbox 결정
            rep_span = max(spans, key=lambda s: len(s.get("text", "")))
            font  = rep_span.get("font", "")
            size  = float(rep_span.get("size", 0.0))
            # line 전체를 감싸는 bbox: 첫 span x0 ~ 마지막 span x1, y는 line wdir 기준
            x0 = min(s["bbox"][0] for s in spans if "bbox" in s)
            y0 = min(s["bbox"][1] for s in spans if "bbox" in s)
            x1 = max(s["bbox"][2] for s in spans if "bbox" in s)
            y1 = max(s["bbox"][3] for s in spans if "bbox" in s)
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


def extract_raw_text(fitz_page: fitz.Page) -> str:
    """단순 텍스트 문자열 추출 (TXT 출력용)."""
    return fitz_page.get_text("text").strip()
