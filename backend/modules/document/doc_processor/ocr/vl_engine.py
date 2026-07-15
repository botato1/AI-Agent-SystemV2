"""PaddleOCR-VL 엔진 — 표/차트 전용 Vision-Language OCR (GPU 전용).

PaddleOCRVL 파이프라인 대신 transformers로 직접 모델 호출.
"""
from __future__ import annotations

from PIL import Image

_model = None
_processor = None


def _patch_create_causal_mask():
    """transformers 5.x에서 create_causal_mask의 파라미터명 변경 호환 패치.
    inputs_embeds(구) → input_embeds(신)
    """
    try:
        import transformers.masking_utils as _mu
        _orig = _mu.create_causal_mask
        def _patched(**kwargs):
            if "inputs_embeds" in kwargs:
                kwargs["input_embeds"] = kwargs.pop("inputs_embeds")
            return _orig(**kwargs)
        _mu.create_causal_mask = _patched
    except Exception:
        pass


def _load():
    global _model, _processor
    if _model is None:
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        _patch_create_causal_mask()
        model_path = "PaddlePaddle/PaddleOCR-VL"
        print("[VL] Loading PaddleOCR-VL via transformers...")
        _model = AutoModelForCausalLM.from_pretrained(
            model_path, trust_remote_code=True, dtype=torch.bfloat16
        ).to("cuda").eval()
        _processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        print("[VL] PaddleOCR-VL loaded on cuda.")
    return _model, _processor


class VLEngine:
    """표/차트 이미지를 Markdown 텍스트로 변환합니다."""

    def __init__(self) -> None:
        self._model, self._processor = _load()

    def run(self, image: Image.Image, fig_type: str = "table") -> str:
        import torch

        prompt = "Table Recognition:" if fig_type == "table_image" else "Chart Recognition:"

        try:
            image = image.convert("RGB")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            inputs = self._processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            ).to("cuda")

            with torch.no_grad():
                outputs = self._model.generate(**inputs, max_new_tokens=1024)

            torch.cuda.empty_cache()

        except Exception as e:
            print(f"[VL] 추론 실패: {e}")
            return ""

        result = self._processor.batch_decode(outputs, skip_special_tokens=True)[0]
        if "assistant" in result.lower():
            result = result.split("assistant")[-1].strip()
        return result.strip()
