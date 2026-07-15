from __future__ import annotations

import glob
import os
import re
from typing import Any

import numpy as np
from PIL import Image

# paddlepaddle-gpu nvidia CUDA DLL 경로 등록 (Windows)
if os.name == "nt":
    import site
    for _sp in site.getsitepackages():
        for _d in glob.glob(os.path.join(_sp, "nvidia", "*", "bin")):
            os.add_dll_directory(_d)

from paddleocr import PaddleOCR

os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("DNNL_DEFAULT_FPMATH_MODE", "STRICT")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _flatten(result: Any) -> list[str]:
    texts: list[str] = []
    if result is None:
        return texts
    if isinstance(result, dict):
        rec_texts = result.get("rec_texts")
        if isinstance(rec_texts, list):
            return [_normalize(str(t)) for t in rec_texts if _normalize(str(t))]
    if isinstance(result, list):
        for item in result:
            texts.extend(_flatten(item))
        return texts
    if isinstance(result, tuple) and len(result) >= 2:
        text_part = result[1]
        if isinstance(text_part, tuple) and text_part:
            t = _normalize(str(text_part[0]))
            if t:
                texts.append(t)
    return texts


class PaddleEngine:
    def __init__(self) -> None:
        self._ocr = self._load()

    def _load(self) -> PaddleOCR:
        try:
            return PaddleOCR(
                lang="korean",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
                device="cpu",
                enable_mkldnn=False,
            )
        except TypeError:
            return PaddleOCR(lang="korean", use_angle_cls=True, show_log=False, enable_mkldnn=False)

    def run(self, image: Image.Image) -> list[str]:
        cv_image = np.array(image)
        result = self._ocr.predict(cv_image)
        lines = _flatten(result)
        return list(dict.fromkeys(lines))
