from __future__ import annotations

import re
import unicodedata

from doc_processor.core.models import TextBlock

# ── 가중치 ────────────────────────────────────────────────────────────────────
# 한글 비율 가중치를 낮춤 — 한글+영어 혼재 문서(기술 문서 등)에서 점수 하락 방지
_W_KOREAN      = 0.15   # 한글 비율 (참고용, 높은 가중치 부여 안 함)
_W_LENGTH      = 0.25   # 문자 수 (추출 성공 여부 가장 중요)
_W_BROKEN      = 0.30   # 깨진 문자 비율 (OCR 품질 핵심 지표)
_W_SPECIAL     = 0.15   # 과도한 특수문자 비율
_W_WHITESPACE  = 0.10   # 공백 비율
_W_STRUCTURE   = 0.05   # 제목/본문 구조 존재 여부

# 깨진 문자로 간주
_BROKEN = frozenset("□▯�\x00")

# 의미 있는 특수문자 (점수 차감 제외)
_ALLOWED_SPECIAL = frozenset(".,!?:;()[]{}%+-=@#/\\\"'…—·")


def _korean_ratio(text: str) -> float:
    if not text:
        return 0.0
    korean = sum(1 for c in text if "가" <= c <= "힣" or "ᄀ" <= c <= "ᇿ")
    return korean / len(text)


def _broken_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for c in text if c in _BROKEN) / len(text)


def _special_char_ratio(text: str) -> float:
    """허용 특수문자를 제외한 나머지 특수문자 비율."""
    if not text:
        return 0.0
    noise = sum(
        1 for c in text
        if not c.isalnum()
        and not c.isspace()
        and c not in _ALLOWED_SPECIAL
        and unicodedata.category(c).startswith("P") is False
    )
    return noise / len(text)


def _whitespace_ratio(text: str) -> float:
    if not text:
        return 1.0
    return sum(1 for c in text if c.isspace()) / len(text)


def _length_score(text: str) -> float:
    """50자 이상이면 만점. 짧을수록 감점."""
    return min(len(text.strip()) / 50.0, 1.0)


def _structure_score(blocks: list[TextBlock]) -> float:
    """title 또는 heading 스타일 블록이 하나라도 있으면 1.0."""
    has_title = any(b.style in ("title", "heading") for b in blocks)
    return 1.0 if has_title else 0.5


def _block_score(block: TextBlock) -> float:
    text = block.text.strip()
    if not text:
        return 0.0

    korean   = _korean_ratio(text)
    length   = _length_score(text)
    broken   = 1.0 - _broken_ratio(text)
    special  = 1.0 - min(_special_char_ratio(text) * 5, 1.0)  # 20% 이상이면 0점
    ws       = 1.0 - min(_whitespace_ratio(text) * 2, 1.0)    # 50% 이상이면 0점

    return (
        korean  * _W_KOREAN +
        length  * _W_LENGTH +
        broken  * _W_BROKEN +
        special * _W_SPECIAL +
        ws      * _W_WHITESPACE
    )


def score(blocks: list[TextBlock]) -> float:
    """TextBlock 리스트의 품질 추정 점수를 반환합니다 (0.0 ~ 1.0).

    블록이 없으면 1.0 (해당 없음).
    """
    if not blocks:
        return 1.0

    block_scores = [_block_score(b) for b in blocks]
    avg = sum(block_scores) / len(block_scores)

    # 구조 보너스 (가중치 적음)
    structure = _structure_score(blocks)
    final = avg * (1 - _W_STRUCTURE) + structure * _W_STRUCTURE

    return round(min(final, 1.0), 3)
