from __future__ import annotations

import fitz


def classify_pdf(pdf_path: str) -> str:
    """PDF 유형을 감지합니다.

    Returns:
        "digital"  — 텍스트 레이어가 충분한 일반 PDF
        "scanned"  — 대부분 이미지로만 구성된 스캔 PDF
        "mixed"    — 디지털 + 스캔이 혼재
    """
    with fitz.open(pdf_path) as doc:
        total = len(doc)
        if total == 0:
            return "digital"

        text_pages = 0
        image_only_pages = 0

        for page in doc:
            text = page.get_text("text").strip()
            blocks = page.get_text("dict")["blocks"]
            has_image = any(b.get("type") == 1 for b in blocks)

            if len(text) > 50:
                text_pages += 1
            elif has_image:
                image_only_pages += 1

        image_ratio = image_only_pages / total
        text_ratio = text_pages / total

        if image_ratio >= 0.7:
            return "scanned"
        elif text_ratio >= 0.7:
            return "digital"
        else:
            return "mixed"
