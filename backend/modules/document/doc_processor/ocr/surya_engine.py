from __future__ import annotations

import re

from PIL import Image


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class SuryaEngine:
    def __init__(self) -> None:
        from surya.inference import SuryaInferenceManager
        from surya.inference.backends.torch import TorchBackend
        from surya.recognition import RecognitionPredictor

        manager = SuryaInferenceManager(backend=TorchBackend())
        self._rec = RecognitionPredictor(manager=manager)

    def run(self, image: Image.Image) -> list[str]:
        results = self._rec([image])
        if not results:
            return []
        lines = [_normalize(line.text) for line in results[0].text_lines if _normalize(line.text)]
        return list(dict.fromkeys(lines))
