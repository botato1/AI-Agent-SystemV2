"""PaddleOCR-VL-1.6 엔진 — 표/차트 전용 Vision-Language OCR (GPU 전용).

PaddleOCR-VL-1.6을 transformers로 직접 호출.
"""
from __future__ import annotations

from PIL import Image

_model = None
_processor = None

MODEL_ID = "PaddlePaddle/PaddleOCR-VL-1.6"


def _patch_causal_mask():
    """transformers 5.x create_causal_mask 파라미터명 변경 호환 패치."""
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
        _patch_causal_mask()

        print(f"[VL-1.6] Loading {MODEL_ID} via transformers...")
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            trust_remote_code=True,
            dtype=torch.bfloat16,
            device_map="auto",
        ).eval()
        _processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
        print("[VL-1.6] PaddleOCR-VL-1.6 loaded.")
    return _model, _processor


def unload() -> None:
    """모델을 GPU 메모리에서 실제로 내립니다 (모듈 전역 참조까지 해제).

    _load()가 모델을 모듈 전역변수(_model)에 캐싱해두기 때문에,
    PaddleVL16Engine 인스턴스를 del 해도 이 전역 참조가 남아있으면
    GPU 메모리가 절대 해제되지 않는다. 반드시 이 함수로 전역변수까지 None 처리해야 함.
    """
    global _model, _processor
    if _model is not None:
        del _model
        del _processor
        _model = None
        _processor = None


class PaddleVL16Engine:
    """표/차트 이미지를 Markdown 텍스트로 변환합니다 (PaddleOCR-VL-1.6)."""

    def __init__(self) -> None:
        self._model, self._processor = _load()

    def run(self, image: Image.Image, fig_type: str = "table") -> str:
        import torch

        if fig_type == "table_image":
            prompt = "Table Recognition:"
        else:
            prompt = "Chart Recognition:"

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
            ).to(self._model.device)

            with torch.no_grad():
                outputs = self._model.generate(**inputs, max_new_tokens=1024)

            # 입력 토큰 제외하고 새로 생성된 부분만 디코딩
            input_len = inputs["input_ids"].shape[1]
            generated_ids = outputs[:, input_len:]
            result = self._processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]

            if self._model.device.type == "cuda":
                torch.cuda.empty_cache()

        except Exception as e:
            print(f"[VL-1.6] 추론 실패: {e}")
            return ""

        return result.strip()
