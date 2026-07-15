"""OCR 품질 필터 + Paddle 결과 정제."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

# ── 전체 텍스트 품질 필터 기준 ─────────────────────────────────────────────────
_MIN_CONFIDENCE    = 0.40
_MIN_CHARS         = 4
_MAX_SPECIAL_RATIO = 0.40
_MAX_REPEAT_RATIO  = 0.60
_MAX_LINE_REPEAT   = 0.50


# ── 라인 단위 쓰레기 필터 ─────────────────────────────────────────────────────

# 의미 없는 짧은 토큰 패턴 (J, B, p., m), u ur 등)
_JUNK_SHORT = re.compile(
    r'^[a-zA-Z]{1,2}[.)]{0,1}$'      # J / B / p. / m)
    r'|^[a-z]{1,2}\s+[a-z]{1,2}$'    # u ur
    r'|^[^가-힣a-zA-Z0-9]{1,3}$'     # 특수문자 1~3개만
)


def _is_junk_line(text: str) -> bool:
    """단일 라인이 OCR 쓰레기인지 판단합니다.

    판단 기준:
        - 한글·영문·숫자가 전혀 없음
        - 알파벳 1글자만인 토큰 (J, B 등)
        - 매우 짧고 의미 없는 기호 조합
    """
    stripped = text.strip()
    if not stripped:
        return True
    # 의미 있는 문자가 전혀 없음
    if not any(c.isalpha() or "가" <= c <= "힣" or c.isdigit() for c in stripped):
        return True
    # 길이 1 — 단독 알파벳/기호
    if len(stripped) == 1:
        return True
    # 알파벳 1글자 + 기호 조합 (p., m), B. 등)
    alpha_count = sum(1 for c in stripped if c.isalpha())
    if len(stripped) <= 3 and alpha_count <= 1 and stripped[0].isascii():
        return True
    # 짧은 소문자 영단어 조각 (u ur, ab cd 등)
    if len(stripped) <= 5:
        words = re.findall(r'[a-z]+', stripped)
        if words and all(len(w) <= 2 for w in words) and not any("가" <= c <= "힣" for c in stripped):
            return True
    return False


# ── 전체 텍스트 품질 필터 ─────────────────────────────────────────────────────

def _special_ratio(text: str) -> float:
    if not text:
        return 1.0
    special = sum(1 for c in text if not c.isalnum() and not c.isspace())
    return special / len(text)


def _repeat_word_ratio(text: str) -> float:
    """단어 반복 비율 — 'Tanzania Tanzania Tanzania' 같은 패턴 감지."""
    words = re.findall(r"\w+", text.lower())
    if len(words) < 4:
        return 0.0
    counts = Counter(words)
    return counts.most_common(1)[0][1] / len(words)


def _line_repeat_ratio(text: str) -> float:
    """동일 라인 반복 비율 — 'Anua\\nAnua\\nAnua' 같은 패턴 감지."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) < 3:
        return 0.0
    counts = Counter(lines)
    return counts.most_common(1)[0][1] / len(lines)


def _is_quality_result(text: str, confidence: float) -> tuple[bool, str]:
    """OCR 결과가 저장할 가치가 있는지 판단합니다.

    Returns:
        (valid, reason) — valid=False 이면 결과 폐기
    """
    if confidence < _MIN_CONFIDENCE:
        return False, f"low_confidence({confidence:.2f})"

    stripped = text.strip()
    if len(stripped) < _MIN_CHARS:
        return False, f"too_short(len={len(stripped)})"

    sr = _special_ratio(stripped)
    if sr > _MAX_SPECIAL_RATIO:
        return False, f"high_special({sr:.2f})"

    rr = _repeat_word_ratio(stripped)
    if rr > _MAX_REPEAT_RATIO:
        return False, f"repeated_words({rr:.2f})"

    lr = _line_repeat_ratio(stripped)
    if lr > _MAX_LINE_REPEAT:
        return False, f"repeated_lines({lr:.2f})"

    return True, "ok"


# ── Voting ────────────────────────────────────────────────────────────────────

def vote(
    paddle_lines: list[str],
    threshold: float = 0.84,
) -> dict[str, Any]:
    """PaddleOCR 결과를 품질 필터링하여 반환합니다.

    Returns:
        {
            "text": str,
            "lines": list[dict],
            "confidence": float,
            "sources": list[str],
            "filtered": bool,
            "filter_reason": str,
        }
    """
    voted: list[dict[str, Any]] = []

    for paddle_line in paddle_lines:
        voted.append({
            "text": paddle_line,
            "confidence": 0.62,
            "source": "paddle_only",
            "paddle": paddle_line,
        })

    # ── 라인 단위 쓰레기 필터 ─────────────────────────────────────────────────
    clean_voted = [v for v in voted if not _is_junk_line(v["text"])]
    if clean_voted:
        voted = clean_voted

    text = "\n".join(item["text"] for item in voted)
    avg_conf = (
        round(sum(item["confidence"] for item in voted) / len(voted), 3)
        if voted else 0.0
    )
    sources = list({item["source"] for item in voted})

    # ── 전체 텍스트 품질 필터 ─────────────────────────────────────────────────
    valid, reason = _is_quality_result(text, avg_conf)

    return {
        "text": text,
        "lines": voted,
        "confidence": avg_conf,
        "sources": sources,
        "filtered": not valid,
        "filter_reason": reason,
    }
