"""OCR Voting + 품질 필터.

PaddleOCR와 Surya OCR 결과를 비교 투표하여 최적 텍스트를 선택합니다.
투표 이전과 이후 두 단계에서 품질 필터를 적용합니다.

Phase 2 강화:
    - 라인 단위 쓰레기 필터 (_is_junk_line)
    - 브랜드/라인 반복 감지 (_line_repeat_ratio)
    - 특수문자 비율 임계값 강화 0.50 → 0.40
    - 최소 문자 수 강화: len <= 3 폐기 (_MIN_CHARS = 4)

Phase 3 강화:
    - 부분 유사 구간(0.10~0.84)에서 둘 다 출력 → 단일 선택
    - clean_surya(태그 제거) 길이 기준으로 paddle vs surya 선택
    - surya 선택 시 clean 텍스트를 저장(태그 오염 방지)
"""
from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

# ── 전체 텍스트 품질 필터 기준 ─────────────────────────────────────────────────
_MIN_CONFIDENCE    = 0.40   # 이 미만이면 결과 폐기
_MIN_CHARS         = 4      # 전체 텍스트가 이 미만이면 폐기
_MAX_SPECIAL_RATIO = 0.40   # 특수문자 비율 > 40% 폐기 (기존 0.50 → 강화)
_MAX_REPEAT_RATIO  = 0.60   # 반복 단어 비율 > 60% 폐기
_MAX_LINE_REPEAT   = 0.50   # 동일 라인 반복 비율 > 50% 폐기 (Anua\nAnua...)


# ── Surya 태그 제거 ───────────────────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r'<[^>]+>')
_LATEX_CMD_RE = re.compile(r'\\[a-zA-Z]+\{[^}]*\}|\\[a-zA-Z]+')

def _clean_surya(text: str) -> str:
    """Surya 출력에서 HTML/LaTeX 태그를 제거한 순수 텍스트를 반환합니다."""
    t = _HTML_TAG_RE.sub("", text)
    t = _LATEX_CMD_RE.sub("", t)
    t = re.sub(r'[{}]', "", t)
    t = re.sub(r'\s+', " ", t).strip()
    return t


# ── 유사도 ────────────────────────────────────────────────────────────────────

# 부분 유사 구간: 이 범위에서 paddle_only + surya_only 둘 다 출력 대신 단일 선택
_SIM_PARTIAL_LOW = 0.10   # 미만이면 완전 무관 → 현행 유지
# 상한은 기존 threshold(0.84)와 동일

def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


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
    surya_lines: list[str],
    threshold: float = 0.84,
) -> dict[str, Any]:
    """PaddleOCR와 Surya OCR 결과를 Voting하여 최적 텍스트를 선택합니다.

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
    used_surya: set[int] = set()
    voted: list[dict[str, Any]] = []

    for paddle_line in paddle_lines:
        best_index = None
        best_score = 0.0
        for idx, surya_line in enumerate(surya_lines):
            if idx in used_surya:
                continue
            score = _similar(paddle_line, surya_line)
            if score > best_score:
                best_score = score
                best_index = idx

        if best_index is not None and best_score >= threshold:
            # 높은 유사도 — 기존 matched 경로: 더 긴 원문 선택
            surya_line = surya_lines[best_index]
            used_surya.add(best_index)
            chosen = surya_line if len(surya_line) >= len(paddle_line) else paddle_line
            line_conf = round((1.0 + best_score) / 2.0, 3)
            voted.append({
                "text": chosen,
                "confidence": line_conf,
                "source": "paddle+surya",
                "paddle": paddle_line,
                "surya": surya_line,
            })
        elif best_index is not None and best_score >= _SIM_PARTIAL_LOW:
            # 부분 유사 구간(0.10~threshold): clean_surya 길이 비교 후 단일 선택
            surya_line = surya_lines[best_index]
            surya_clean = _clean_surya(surya_line)
            used_surya.add(best_index)  # surya_only 중복 출력 방지
            if len(surya_clean) >= len(paddle_line):
                chosen = surya_clean
                source = "partial+surya"
            else:
                chosen = paddle_line
                source = "partial+paddle"
            voted.append({
                "text": chosen,
                "confidence": 0.55,
                "source": source,
                "paddle": paddle_line,
                "surya": surya_line,
            })
        else:
            # 완전 무관(score < 0.10) — 기존 paddle_only 유지
            voted.append({
                "text": paddle_line,
                "confidence": 0.62,
                "source": "paddle_only",
                "paddle": paddle_line,
                "surya": "",
            })

    for idx, surya_line in enumerate(surya_lines):
        if idx not in used_surya:
            voted.append({
                "text": surya_line,
                "confidence": 0.62,
                "source": "surya_only",
                "paddle": "",
                "surya": surya_line,
            })

    # ── 라인 단위 쓰레기 필터 (투표 후) ──────────────────────────────────────
    clean_voted = [v for v in voted if not _is_junk_line(v["text"])]
    # 전부 제거되지 않도록 — 쓰레기 라인이 과반수면 전체 폐기 예정이므로 원본 유지
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
