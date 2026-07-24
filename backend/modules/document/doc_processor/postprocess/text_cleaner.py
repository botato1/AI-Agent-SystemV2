from __future__ import annotations

import re

from doc_processor.core.models import TextBlock
from doc_processor.postprocess.spacing_restorer import restore_multiline, restore_spacing

# ── HTML/XML 태그 제거 ────────────────────────────────────────────────────────
_HTML_TAG = re.compile(r"<[^>]+>")

# ── LaTeX 명령어 제거 ─────────────────────────────────────────────────────────
# \cmd{content} → content (내부 텍스트 보존, 중첩 처리를 위해 반복 적용)
# \cmd           → ""     (인수 없는 기호 명령어)
_LATEX_WITH_ARG = re.compile(r'\\[a-zA-Z]+\{([^{}]*)\}')
_LATEX_NO_ARG   = re.compile(r'\\[a-zA-Z]+')

# ── 외래 스크립트 토큰 제거 ───────────────────────────────────────────────────
# 한국어 기술 문서에서 정상적으로 허용되는 Unicode 범위 (화이트리스트)
#
# 허용:
#   U+0000-024F  Basic Latin + Latin Extended A/B (영문, 유럽어, ASCII)
#   U+0250-02FF  IPA Extensions / Spacing Modifier Letters
#   U+0300-036F  Combining Diacritical Marks
#   U+0370-03FF  Greek and Coptic (α β γ Σ Ω 등 수식)
#   U+2000-2BFF  General Punctuation · Math · Arrows · Technical Symbols
#                (•, …, ±, ×, ÷, ℃, ℓ, →, ∑, √ 등)
#   U+3000-33FF  CJK Symbols · CJK Compat (㎝, ㎞, ㎏ 등 단위 포함)
#   U+3040-30FF  Japanese Hiragana / Katakana
#   U+3130-318F  Hangul Compatibility Jamo
#   U+4E00-9FFF  CJK Unified Ideographs (한자)
#   U+1100-11FF  Hangul Jamo
#   U+AC00-D7A3  Hangul Syllables (완성형 한글)
#   U+F900-FFEF  CJK Compat Ideographs · Halfwidth/Fullwidth Forms
#
# 이 범위 밖의 문자 = "외래 스크립트" (Cyrillic/Arabic/Bengali/Gujarati 등)
# → 해당 문자만으로 구성된 토큰을 제거 (줄 전체 삭제 금지)
def _is_allowed(cp: int) -> bool:
    """코드포인트가 한국어 기술 문서 화이트리스트에 속하면 True."""
    return (
        cp <= 0x024F                       or  # Basic Latin + Latin Extended A/B
        0x0250 <= cp <= 0x02FF             or  # IPA / Spacing Modifiers
        0x0300 <= cp <= 0x036F             or  # Combining Diacritical Marks
        0x0370 <= cp <= 0x03FF             or  # Greek (α β γ Σ)
        0x2000 <= cp <= 0x2BFF             or  # Punctuation / Math / Symbols
        0x3000 <= cp <= 0x33FF             or  # CJK Symbols + ㎝㎞ 단위
        0x3040 <= cp <= 0x30FF             or  # Japanese
        0x3130 <= cp <= 0x318F             or  # Hangul Compat Jamo
        0x4E00 <= cp <= 0x9FFF             or  # CJK Unified
        0x1100 <= cp <= 0x11FF             or  # Hangul Jamo
        0xAC00 <= cp <= 0xD7A3             or  # Hangul Syllables
        0xF900 <= cp <= 0xFFEF                 # CJK Compat + Fullwidth
    )


def _is_foreign_script_token(token: str) -> bool:
    """토큰이 외래 스크립트 문자로만 구성되어 있으면 True.

    판정 조건:
      1. 화이트리스트 밖의 문자가 1개 이상 포함
      2. 화이트리스트 안의 알파벳/숫자 문자가 0개 (정상 텍스트 없음)

    '정상 알파벳/숫자'란: 화이트리스트 내에서 letter 또는 digit인 문자.
    공백·구두점·수학기호 단독 토큰은 이 필터를 통과하지 않음.
    """
    non_space = [c for c in token if not c.isspace()]
    if not non_space:
        return False

    has_foreign   = any(not _is_allowed(ord(c)) for c in non_space)
    has_normal_ld = any(
        _is_allowed(ord(c)) and (c.isalpha() or c.isdigit())
        for c in non_space
    )
    return has_foreign and not has_normal_ld


# 공백 기준 토큰 분리 패턴 (연속 공백 보존을 위해 split 대신 re.split 사용)
_TOKEN_SPLIT = re.compile(r"(\s+)")

# ── OCR 오타 교정 패턴 ────────────────────────────────────────────────────────
_OCR_CORRECTIONS: list[tuple[re.Pattern, str]] = [
    # 구두점 정규화
    (re.compile(r"\.{3,}"),                         "…"),
    (re.compile(r"-{2,}"),                          "—"),
    # 숫자/문자 혼동 (확실한 맥락만)
    (re.compile(r"(?<!\w)O(?=\d)"),                 "0"),  # O1 → 01
    (re.compile(r"(?<=\d)O(?!\w)"),                 "0"),  # 1O → 10
    (re.compile(r"(?<!\w)l(?=\d)"),                 "1"),  # l2 → 12
    (re.compile(r"(?<=\d)l(?!\w)"),                 "1"),  # 2l → 21
    # 줄바꿈 하이픈 제거 (한글)
    (re.compile(r"(?<=[가-힣])-\n(?=[가-힣])"),     ""),
    # rn → m 오인식 (한글 인접)
    (re.compile(r"rn(?=[가-힣\s])"),                "m"),
    (re.compile(r"(?<=[가-힣\s])rn"),               "m"),
]

# 숫자 사이 공백 정규화: "1 0 0 0" → "1000" (4자리 이상 연속)
_DIGIT_SPACE = re.compile(r"\b(\d)(?:\s(\d)){3,}\b")

# ── 의미 없는 라인 패턴 ───────────────────────────────────────────────────────
# 특수문자만 1~4글자이거나 공백만인 라인
_NOISE_LINE = re.compile(r"^[\s\W]{1,4}$")

# 특수문자 비율이 이 값 초과이면 라인 제거
_SPECIAL_RATIO_THRESHOLD = 0.6

# 이 글자 수 미만이고 한글·영문·숫자가 없는 라인 제거
_MIN_MEANINGFUL_LEN = 2


def _remove_foreign_script_tokens(text: str) -> str:
    """외래 스크립트 토큰을 줄 단위로 제거합니다.

    규칙:
    - 공백을 기준으로 토큰을 분리
    - 외래 스크립트 문자만으로 구성된 토큰은 제거
    - 정상 문자가 포함된 줄은 보존 (줄 전체 삭제 금지)
    - 제거 후 남은 연속 공백은 단일 공백으로 정규화

    예시:
      "ঌইفӝ\n• 해발 고도가 높을수록..."  →  "• 해발 고도가 높을수록..."
      "҃Ҋ 안전벨트를 착용하십시오."     →  "안전벨트를 착용하십시오."
      "570 ± 25 g"                    →  "570 ± 25 g"  (변경 없음)
    """
    lines = text.split("\n")
    cleaned_lines: list[str] = []

    for line in lines:
        # 공백과 토큰을 교대로 분리 (공백 구조 보존)
        parts = _TOKEN_SPLIT.split(line)   # [tok, sep, tok, sep, ...]
        kept: list[str] = []
        for part in parts:
            if _TOKEN_SPLIT.fullmatch(part):
                # 공백 구간 — 그대로 유지 (나중에 정규화)
                kept.append(part)
            elif _is_foreign_script_token(part):
                # 외래 스크립트 토큰 — 제거 (빈 문자열로 치환)
                kept.append("")
            else:
                kept.append(part)

        # 연결 후 선두/후미 공백 제거 + 내부 연속 공백 정규화
        joined = "".join(kept).strip()
        joined = re.sub(r" {2,}", " ", joined)
        cleaned_lines.append(joined)

    return "\n".join(cleaned_lines)


def _remove_html_tags(text: str) -> str:
    return _HTML_TAG.sub("", text)


def _remove_latex_commands(text: str) -> str:
    """LaTeX 명령어를 제거합니다.

    \\cmd{content} → content (중첩 구조는 최대 5회 반복으로 처리)
    \\cmd          → ""      (인수 없는 기호 명령어)
    남은 {}        → ""      (고립된 중괄호)
    """
    prev = None
    for _ in range(5):
        if text == prev:
            break
        prev = text
        text = _LATEX_WITH_ARG.sub(r'\1', text)
    text = _LATEX_NO_ARG.sub("", text)
    text = re.sub(r'[{}]', "", text)
    return text


def _apply_ocr_corrections(text: str) -> str:
    for pattern, replacement in _OCR_CORRECTIONS:
        text = pattern.sub(replacement, text)
    # 숫자 사이 공백 제거 (4자리 이상 연속: "1 2 3 4" → "1234")
    text = _DIGIT_SPACE.sub(lambda m: m.group(0).replace(" ", ""), text)
    return text


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _special_ratio(line: str) -> float:
    if not line:
        return 1.0
    special = sum(1 for c in line if not c.isalnum() and not c.isspace())
    return special / len(line)


def _has_meaningful_content(line: str) -> bool:
    """한글·영문·숫자가 하나라도 있으면 의미 있는 라인."""
    return any(c.isalnum() or "가" <= c <= "힣" for c in line)


def _filter_noise_lines(text: str) -> str:
    lines = text.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")  # 빈 줄은 유지 (문단 구분)
            continue
        if _NOISE_LINE.match(stripped):
            continue
        if len(stripped) <= _MIN_MEANINGFUL_LEN and not _has_meaningful_content(stripped):
            continue
        if _special_ratio(stripped) > _SPECIAL_RATIO_THRESHOLD:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _clean(text: str) -> str:
    text = _remove_html_tags(text)
    text = _remove_latex_commands(text)
    text = _apply_ocr_corrections(text)
    text = _remove_foreign_script_tokens(text)   # 외래 스크립트 아이콘 토큰 제거
    text = _filter_noise_lines(text)
    text = restore_spacing(text)                 # 자간 분리 한글 복원 (단일 줄)
    text = restore_multiline(text)               # 멀티라인 단편화 보수적 복원
    text = _normalize_whitespace(text)
    return text


def clean_text_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    cleaned: list[TextBlock] = []
    for block in blocks:
        text = _clean(block.text)
        if text:
            cleaned.append(TextBlock(
                text=text,
                bbox=block.bbox,
                font=block.font,
                size=block.size,
                style=block.style,
            ))
    return cleaned


def clean_ocr_text(text: str) -> str:
    """이미지/OCR 텍스트 정제 (단일 문자열용)."""
    return _clean(text)
