from __future__ import annotations

from doc_processor.core.models import ImageBlock, PageContent
from doc_processor.postprocess import layout_restorer, table_cleaner, text_cleaner
from doc_processor.postprocess.vertical_text_restorer import restore_vertical_text


class PostProcessor:
    """파싱/OCR 결과를 정제하는 후처리 파이프라인."""

    def process(self, content: PageContent) -> PageContent:
        # 1. 텍스트 정제 → 계층 구조 복원
        cleaned_text = text_cleaner.clean_text_blocks(content.text)
        restored_text = layout_restorer.restore_hierarchy(cleaned_text)

        # 2. 표 정제
        cleaned_tables = table_cleaner.clean_tables(content.tables)

        # 3. 이미지 OCR 텍스트 정제 (정제 → 세로 텍스트 복원)
        cleaned_images: list[ImageBlock] = []
        for img in content.images:
            cleaned_ocr = text_cleaner.clean_ocr_text(img.ocr_text)
            cleaned_ocr = restore_vertical_text(cleaned_ocr)  # 세로 텍스트 복원

            # debug 딕셔너리 유지 + final_text(PostProcess 후) 기록
            new_debug = None
            if img.debug is not None:
                new_debug = dict(img.debug)
                new_debug["final_text"] = cleaned_ocr   # PostProcess 후 최종 텍스트

            cleaned_images.append(ImageBlock(
                bbox=img.bbox,
                ocr_text=cleaned_ocr,
                voting_confidence=img.voting_confidence,
                source_engines=img.source_engines,
                paddle_lines=img.paddle_lines,
                quality_score=img.quality_score,
                debug=new_debug,
            ))

        return PageContent(
            text=restored_text,
            tables=cleaned_tables,
            images=cleaned_images,
            charts=content.charts,
        )
