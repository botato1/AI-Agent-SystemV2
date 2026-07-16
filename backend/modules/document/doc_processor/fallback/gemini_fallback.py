from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from PIL import Image

from doc_processor.core.models import ConfidenceScore, PageContent

if TYPE_CHECKING:
    pass

FALLBACK_THRESHOLD = 0.90

_PROMPT_TEMPLATE = """
다음은 PDF 페이지의 자동 추출 결과입니다.
신뢰도가 낮은 항목을 이미지에서 직접 확인하여 수정해주세요.

신뢰도 낮은 항목:
{low_items}

현재 추출 결과 (Markdown):
{current_markdown}

지시사항:
1. 이미지에서 텍스트를 직접 읽어 OCR 오류를 수정하세요.
2. 표가 있으면 Markdown Table 형식으로 재출력하세요.
3. 차트/그래프가 있으면 제목과 데이터를 설명하세요.
4. 수정된 내용을 아래 JSON 형식으로 반환하세요.

반환 형식:
{{
  "text": "수정된 전체 텍스트",
  "tables": ["Markdown Table 1", "Markdown Table 2"],
  "images": ["이미지 설명 1"],
  "charts": ["차트 설명 1"]
}}
""".strip()


def _content_to_markdown(content: PageContent) -> str:
    parts: list[str] = []

    if content.text:
        parts.append("## 텍스트\n" + " ".join(b.text for b in content.text))

    for i, table in enumerate(content.tables):
        parts.append(f"## 표 {i+1}\n{table.markdown}")

    for i, img in enumerate(content.images):
        parts.append(f"## 이미지 {i+1}\n{img.ocr_text}")

    return "\n\n".join(parts)


def _parse_gemini_response(response_text: str, original: PageContent) -> PageContent:
    """Gemini 응답 JSON을 파싱해 PageContent를 보정합니다.
    파싱 실패 시 원본을 그대로 반환합니다.
    """
    try:
        # 응답에서 JSON 블록만 추출
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not match:
            return original
        data = json.loads(match.group())
    except (json.JSONDecodeError, AttributeError):
        return original

    from doc_processor.core.models import ImageBlock, TableBlock, TextBlock

    patched = PageContent()

    # 텍스트 보정
    corrected_text = data.get("text", "").strip()
    if corrected_text:
        patched.text = [TextBlock(text=corrected_text, bbox=[0, 0, 0, 0], style="body")]
    else:
        patched.text = original.text

    # 표 보정
    corrected_tables = data.get("tables", [])
    if corrected_tables:
        patched.tables = [
            TableBlock(data=[], markdown=md, bbox=[0, 0, 0, 0])
            for md in corrected_tables
        ]
    else:
        patched.tables = original.tables

    # 이미지 보정
    corrected_images = data.get("images", [])
    if corrected_images and original.images:
        patched.images = []
        for i, orig_img in enumerate(original.images):
            description = corrected_images[i] if i < len(corrected_images) else orig_img.ocr_text
            patched.images.append(ImageBlock(
                bbox=orig_img.bbox,
                ocr_text=description,
                voting_confidence=orig_img.voting_confidence,
                source_engines=orig_img.source_engines + ["gemini"],
                paddle_lines=orig_img.paddle_lines,
                surya_lines=orig_img.surya_lines,
            ))
    else:
        patched.images = original.images

    patched.charts = original.charts
    return patched


class GeminiFallback:
    """Gemini Vision API를 이용해 낮은 신뢰도 페이지를 재검증합니다.

    API 키는 생성자에서 주입받습니다.
    키가 없으면 enabled=False로 인스턴스를 생성하세요 — should_run()이 항상 False를 반환합니다.
    """

    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash") -> None:
        self.enabled = bool(api_key)
        self._model_name = model
        self._client = None

        if self.enabled:
            self._client = self._init_client(api_key, model)

    def _init_client(self, api_key: str, model: str):
        try:
            import google.generativeai as genai  # type: ignore[import]
            genai.configure(api_key=api_key)
            return genai.GenerativeModel(model)
        except ImportError as e:
            raise ImportError(
                "google-generativeai 패키지가 필요합니다.\n"
                "pip install google-generativeai"
            ) from e

    def should_run(self, confidence: ConfidenceScore) -> bool:
        if not self.enabled:
            return False
        return confidence.any_below(FALLBACK_THRESHOLD)

    def verify(
        self,
        page_image: Image.Image,
        content: PageContent,
        confidence: ConfidenceScore,
    ) -> PageContent:
        """신뢰도 낮은 항목을 Gemini로 재검증하고 보정된 PageContent를 반환합니다."""
        if not self.enabled:
            return content

        low_items = {
            k: v
            for k, v in confidence.to_dict().items()
            if v < FALLBACK_THRESHOLD
        }
        prompt = _PROMPT_TEMPLATE.format(
            low_items=json.dumps(low_items, ensure_ascii=False),
            current_markdown=_content_to_markdown(content),
        )

        response = self._client.generate_content([page_image, prompt])  # type: ignore[union-attr]
        return _parse_gemini_response(response.text, content)
