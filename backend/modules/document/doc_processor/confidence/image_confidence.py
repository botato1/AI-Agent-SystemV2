from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from doc_processor.core.models import ImageBlock

# ── 가중치 ────────────────────────────────────────────────────────────────────
_W_VOTING      = 0.30   # Paddle ↔ Surya Voting 일치도
_W_LENGTH      = 0.15   # OCR 텍스트 길이
_W_KOREAN      = 0.15   # 한글 비율
_W_NOISE       = 0.20   # OCR 노이즈 비율
_W_SPECIAL     = 0.10   # 과도한 특수문자 비율
_W_REPEAT      = 0.10   # 반복 단어 비율 (Tanzania Tanzania... 패턴)

# OCR 노이즈 패턴 (단독으로 등장하는 의미없는 문자열)
_NOISE_PATTERNS = [
    re.compile(r"^[^가-힣a-zA-Z0-9]{1,3}$"),  # 특수문자만 1~3글자
    re.compile(r"^\s+$"),                        # 공백만
    re.compile(r"^[.\-_|/\\]+$"),               # 구분자만
]


def _is_noise_line(line: str) -> bool:
    return any(p.match(line.strip()) for p in _NOISE_PATTERNS)


def _noise_ratio(text: str) -> float:
    """전체 라인 중 노이즈 라인 비율."""
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return 1.0
    noise = sum(1 for l in lines if _is_noise_line(l))
    return noise / len(lines)


def _korean_ratio(text: str) -> float:
    if not text.strip():
        return 0.0
    korean = sum(1 for c in text if "가" <= c <= "힣")
    return korean / len(text)


def _special_ratio(text: str) -> float:
    if not text.strip():
        return 0.0
    special = sum(
        1 for c in text
        if not c.isalnum() and not c.isspace() and not ("가" <= c <= "힣")
    )
    return special / len(text)


def _length_score(text: str) -> float:
    """100자 이상이면 만점."""
    return min(len(text.strip()) / 100.0, 1.0)


def _voting_similarity(paddle_lines: list[str], surya_lines: list[str]) -> float:
    """Paddle과 Surya 결과 전체 텍스트의 유사도."""
    paddle_text = " ".join(paddle_lines).strip()
    surya_text  = " ".join(surya_lines).strip()

    if not paddle_text and not surya_text:
        return 0.0
    if not paddle_text or not surya_text:
        return 0.4  # 한쪽만 있으면 낮은 점수

    return SequenceMatcher(None, paddle_text, surya_text).ratio()


def _repeat_word_score(text: str) -> float:
    """반복 단어가 많을수록 낮은 점수 (Tanzania Tanzania... 패턴)."""
    words = re.findall(r"\w+", text.lower())
    if len(words) < 4:
        return 1.0
    counts = Counter(words)
    most_common_count = counts.most_common(1)[0][1]
    repeat_ratio = most_common_count / len(words)
    return 1.0 - min(repeat_ratio * 2, 1.0)  # 50% 이상 반복이면 0점


def _image_score(img: ImageBlock) -> float:
    text = img.ocr_text.strip()
    if not text:
        return 0.0

    voting  = _voting_similarity(img.paddle_lines, img.surya_lines)
    length  = _length_score(text)
    korean  = _korean_ratio(text)
    noise   = 1.0 - _noise_ratio(text)
    special = 1.0 - min(_special_ratio(text) * 3, 1.0)
    repeat  = _repeat_word_score(text)

    return (
        voting  * _W_VOTING +
        length  * _W_LENGTH +
        korean  * _W_KOREAN +
        noise   * _W_NOISE +
        special * _W_SPECIAL +
        repeat  * _W_REPEAT
    )


def score(images: list[ImageBlock]) -> float:
    """ImageBlock 리스트의 품질 추정 점수를 반환합니다 (0.0 ~ 1.0).

    이미지가 없으면 1.0 (해당 없음).
    """
    if not images:
        return 1.0

    img_scores = [_image_score(img) for img in images]
    return round(sum(img_scores) / len(img_scores), 3)
