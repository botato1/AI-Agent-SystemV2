from __future__ import annotations

from doc_processor.confidence import image_confidence, table_confidence, text_confidence
from doc_processor.core.models import ConfidenceScore, PageContent


class ConfidenceEngine:
    """페이지 콘텐츠의 품질 추정 점수를 계산합니다.

    각 점수는 "OCR 정확도"가 아니라 "결과물 품질 추정치"입니다.
    실제 정답 없이 규칙 기반으로 계산합니다.
    """

    def compute(self, content: PageContent) -> ConfidenceScore:
        text  = text_confidence.score(content.text)
        table = table_confidence.score(content.tables)
        image = image_confidence.score(content.images)
        chart = 1.0  # Chart 미구현

        # overall: 존재하는 항목만 평균 (없는 항목은 제외)
        active = [
            v for v, blocks in [
                (text,  content.text),
                (table, content.tables),
                (image, content.images),
            ]
            if blocks
        ]
        overall = round(sum(active) / len(active), 3) if active else 1.0

        return ConfidenceScore(
            text=text,
            table=table,
            image=image,
            chart=chart,
            overall=overall,
        )
