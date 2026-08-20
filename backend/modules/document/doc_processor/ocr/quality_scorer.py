"""OCR 품질 점수 계산기 (관측 전용).

⚠ 이 모듈은 OCR 결과를 제거하거나 자동 분류하지 않습니다.
품질을 정량적으로 관측하기 위한 측정 도구입니다.

quality_score (0.0 ~ 1.0):
    값이 낮을수록 노이즈/가비지일 가능성이 높습니다.
    값이 높아도 유효 텍스트라고 보장하지 않습니다.
    자동 필터링 기준으로 사용하지 마세요.

설계 원칙 — 범용 문서 적용:
    ✅ 짧은 영문(EBITDA, ROE, B2B, SKU, Q1) 패널티 없음
    ✅ 숫자 위주(70.9%, Q1 2024) 패널티 없음
    ✅ 한글/영문/숫자 혼합 문서 모두 동작
    ❌ 특정 테스트 파일(실리콘투 IR 등)에 최적화 없음
    ❌ 도메인 특화 사전/규칙 없음

측정 항목:
    1. 알파뉴메릭 비율  (0.45) — ASCII 알파벳+숫자+한글 비율
    2. 유효 라인 비율   (0.35) — 알파뉴메릭 포함 라인 비율
    3. 반복 패턴 패널티 (0.20) — 동일 라인 과도 반복 감지

알려진 한계:
    - 매우 짧은 문자열(1~3자)에서 판별력 약함
      예: '√3' → 숫자 1자 포함으로 score 높게 나올 수 있음
    - LaTeX 명령어(\sqrt, \overline)는 ASCII 영문자 다수 포함으로
      score가 높게 나올 수 있음. 실제 OCR 엔진은 LaTeX를 출력하지
      않으므로 실사용에서는 큰 문제 없음.

useful 판정 임계값:
    QUALITY_USEFUL_THRESHOLD = 0.35
    quality_score >= 이 값이면 useful_count 증가 (통계용)
    이 임계값은 결과 제거에 사용되지 않습니다.
"""
from __future__ import annotations

from collections import Counter

# useful 판정 임계값 (통계 집계 전용, 자동 필터링 아님)
QUALITY_USEFUL_THRESHOLD: float = 0.35

# 가중치
_W_ALPHA  = 0.45
_W_LINE   = 0.35
_W_REPEAT = 0.20

# alpha_score 포화 임계값 (이 비율 이상이면 만점)
_ALPHA_SATURATION = 0.40


def calculate_quality_score(text: str) -> float:
    """OCR 결과 텍스트의 품질 점수를 계산합니다 (0.0 ~ 1.0).

    Args:
        text: OCR 결과 텍스트 (개행 포함 가능)

    Returns:
        0.0 ~ 1.0 사이의 품질 점수.
        0.0 에 가까울수록 노이즈 가능성 높음.
        관측 목적으로만 사용하며 자동 필터링에 쓰지 마세요.
    """
    stripped = text.strip()
    if not stripped:
        return 0.0

    # ── Component 1: 알파뉴메릭 비율 ─────────────────────────────────────────
    # ASCII 알파벳/숫자 + 한글 → 표준 문서 문자
    # 단, 영문/숫자만 있는 짧은 결과(EBITDA, 70.9% 등) 패널티 없음
    non_space = stripped.replace(' ', '').replace('\n', '').replace('\t', '')
    if not non_space:
        return 0.0

    alnum_ko = sum(
        1 for c in non_space
        if (c.isascii() and c.isalnum()) or ('가' <= c <= '힣')
    )
    alpha_ratio = alnum_ko / len(non_space)
    alpha_score = min(alpha_ratio / _ALPHA_SATURATION, 1.0)

    # ── Component 2: 유효 라인 비율 ──────────────────────────────────────────
    # 유효 라인 = 알파뉴메릭 또는 한글이 1자 이상 포함
    # 특수문자/기호만인 라인(√, ω, Θ)을 낮게 평가
    lines = [ln.strip() for ln in stripped.split('\n') if ln.strip()]
    if not lines:
        return 0.0

    valid_lines = sum(
        1 for ln in lines
        if any(
            (c.isascii() and c.isalnum()) or ('가' <= c <= '힣')
            for c in ln
        )
    )
    line_score = valid_lines / len(lines)

    # ── Component 3: 반복 패턴 패널티 ────────────────────────────────────────
    # 동일 라인이 50% 이상 반복이면 0점 (OCR 노이즈 패턴)
    if len(lines) >= 3:
        counts = Counter(lines)
        repeat_ratio = counts.most_common(1)[0][1] / len(lines)
    else:
        repeat_ratio = 0.0
    repeat_score = max(1.0 - repeat_ratio * 2, 0.0)

    # ── 합산 ─────────────────────────────────────────────────────────────────
    return round(
        alpha_score  * _W_ALPHA  +
        line_score   * _W_LINE   +
        repeat_score * _W_REPEAT,
        3,
    )


def is_useful(text: str) -> bool:
    """quality_score >= QUALITY_USEFUL_THRESHOLD 여부를 반환합니다.

    useful_count 통계 집계 전용입니다.
    이 함수의 결과로 OCR 텍스트를 제거하지 마세요.
    """
    return calculate_quality_score(text) >= QUALITY_USEFUL_THRESHOLD
