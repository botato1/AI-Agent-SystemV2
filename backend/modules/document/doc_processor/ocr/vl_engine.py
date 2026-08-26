"""Qwen3-VL 엔진 — 표/차트 전용 Vision-Language OCR (GPU 전용).

Qwen/Qwen3-VL-8B-Instruct 모델을 transformers로 직접 호출.
"""
from __future__ import annotations

from PIL import Image

_model = None
_processor = None

MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"


def _load():
    global _model, _processor
    if _model is None:
        import torch
        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor

        print(f"[VL] Loading {MODEL_ID} via transformers...")
        _model = Qwen3VLForConditionalGeneration.from_pretrained(
            MODEL_ID,
            dtype=torch.bfloat16,
            device_map="auto",
        ).eval()
        _processor = AutoProcessor.from_pretrained(MODEL_ID)
        print("[VL] Qwen3-VL loaded.")
    return _model, _processor


def unload() -> None:
    """모델을 GPU 메모리에서 실제로 내립니다 (모듈 전역 참조까지 해제).

    _load()가 모델을 모듈 전역변수(_model)에 캐싱해두기 때문에,
    VLEngine 인스턴스를 del 해도 이 전역 참조가 남아있으면
    GPU 메모리가 절대 해제되지 않는다. 반드시 이 함수로 전역변수까지 None 처리해야 함.
    """
    global _model, _processor
    if _model is not None:
        del _model
        del _processor
        _model = None
        _processor = None


class VLEngine:
    """표/차트 이미지를 Markdown 텍스트로 변환합니다."""

    def __init__(self) -> None:
        self._model, self._processor = _load()

    def run(self, image: Image.Image, fig_type: str = "table") -> str:
        import torch

        if fig_type == "table_image":
            prompt = "이 이미지의 표를 Markdown 테이블 형식으로 변환해 주세요."
        elif fig_type == "diagram":
            prompt = (
                "이 이미지는 인포그래픽/다이어그램입니다. 표나 차트 데이터로 억지로 정리하지 말고, "
                "제목, 단계, 박스, 번호 등 원래 구조를 유지한 Markdown(제목은 #, 단계는 번호 목록, "
                "항목은 - 로 표기)으로 안에 있는 모든 텍스트를 정리해 주세요. 설명이나 요약은 추가하지 마세요."
            )
        else:
            prompt = "이 차트의 데이터를 마크다운 표 형식으로만 정리해 주세요. 제목은 ### 으로 시작하고, 설명이나 요약은 추가하지 마세요."

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
                # do_sample=False: 기본 생성 설정(샘플링)이 실행마다 다른 결과를 내서
                # 같은 차트를 재해석할 때마다 편차가 컸음 - 결정적 생성으로 고정
                outputs = self._model.generate(**inputs, max_new_tokens=1024, do_sample=False)

            # 입력 토큰 제외하고 새로 생성된 부분만 디코딩
            input_len = inputs["input_ids"].shape[1]
            generated_ids = outputs[:, input_len:]
            result = self._processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]

            if self._model.device.type == "cuda":
                torch.cuda.empty_cache()

        except Exception as e:
            print(f"[VL] 추론 실패: {e}")
            return ""

        return result.strip()