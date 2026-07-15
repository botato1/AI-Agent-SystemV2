from __future__ import annotations

from doc_processor.core.models import TextBlock

_STYLE_PREFIX: dict[str, str] = {
    "title": "# ",
    "heading": "## ",
    "body": "",
    "caption": "_",
}
_STYLE_SUFFIX: dict[str, str] = {
    "caption": "_",
}

# body 블록을 병합할 때 세로 간격 허용 기준 (pt)
# 이 값보다 y 간격이 크면 다른 문단으로 판단
_PARA_GAP_THRESHOLD = 5.0


def _bbox_bottom(block: TextBlock) -> float:
    return block.bbox[3] if len(block.bbox) >= 4 else 0.0


def _bbox_top(block: TextBlock) -> float:
    return block.bbox[1] if len(block.bbox) >= 4 else 0.0


def restore_hierarchy(blocks: list[TextBlock]) -> list[TextBlock]:
    """스타일 기반으로 블록을 병합합니다.

    - title / heading: 같은 스타일이 연속되고 y 간격이 작으면 병합 (제목이 단어 단위로 쪼개진 경우)
    - body: y 간격이 _PARA_GAP_THRESHOLD 이하인 블록끼리만 병합 (문단 보존)
    - caption: 단독 유지
    """
    if not blocks:
        return blocks

    merged: list[TextBlock] = []
    buffer: list[TextBlock] = []
    buffer_style: str = ""

    def flush_buffer() -> None:
        if not buffer:
            return
        # title/heading은 공백으로 이어붙임
        # body는 줄바꿈으로 이어붙임 (문단 구조 보존)
        sep = " " if buffer_style in ("title", "heading") else "\n"
        combined = sep.join(b.text for b in buffer)
        merged.append(TextBlock(
            text=combined,
            bbox=buffer[0].bbox,
            font=buffer[0].font,
            size=buffer[0].size,
            style=buffer_style,
        ))
        buffer.clear()

    for block in blocks:
        style = block.style

        if style == "caption":
            flush_buffer()
            merged.append(block)
            buffer_style = ""
            continue

        if not buffer:
            buffer.append(block)
            buffer_style = style
            continue

        same_style = (style == buffer_style)
        prev_bottom = _bbox_bottom(buffer[-1])
        curr_top = _bbox_top(block)
        gap = curr_top - prev_bottom

        if same_style and gap <= _PARA_GAP_THRESHOLD:
            buffer.append(block)
        else:
            flush_buffer()
            buffer.append(block)
            buffer_style = style

    flush_buffer()
    return merged


def to_markdown_document(blocks: list[TextBlock]) -> str:
    lines: list[str] = []
    for block in blocks:
        prefix = _STYLE_PREFIX.get(block.style, "")
        suffix = _STYLE_SUFFIX.get(block.style, "")
        lines.append(f"{prefix}{block.text}{suffix}")
    return "\n\n".join(lines)
