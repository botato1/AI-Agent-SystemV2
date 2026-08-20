from __future__ import annotations

from pathlib import Path

from doc_processor.core.models import DocumentResult


def _format_table(data: list[list]) -> str:
    lines = []
    for row in data:
        cells = [str(c).replace("\n", " ") if c is not None else "" for c in row]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def to_txt(doc: DocumentResult) -> str:
    lines: list[str] = []
    lines.append(f"출처: {doc.source}")
    lines.append(f"PDF 유형: {doc.pdf_type}")
    lines.append("=" * 60)

    for page in doc.pages:
        lines.append(f"\n{'='*60}")
        lines.append(f"[ Page {page.page} ]")
        lines.append(
            f"Confidence — text:{page.confidence.text}  "
            f"table:{page.confidence.table}  "
            f"image:{page.confidence.image}"
        )
        lines.append("=" * 60)

        if page.content.text:
            lines.append("\n[텍스트]")
            lines.append(" ".join(b.text for b in page.content.text))

        for i, table in enumerate(page.content.tables):
            lines.append(f"\n[표 {i+1}]")
            lines.append(_format_table(table.data))

        for i, img in enumerate(page.content.images):
            if img.ocr_text.strip():
                lines.append(f"\n[이미지 OCR #{i+1}]")
                lines.append(img.ocr_text)

        if not page.content.text and not page.content.tables and not page.content.images:
            lines.append("\n(내용 없음)")

    return "\n".join(lines)


def save_txt(doc: DocumentResult, output_path: str) -> Path:
    path = Path(output_path)
    path.write_text(to_txt(doc), encoding="utf-8")
    return path
