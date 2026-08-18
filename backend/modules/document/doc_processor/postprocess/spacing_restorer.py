"""자간 분리 텍스트 복원기 + 단어 사이 띄어쓰기 복원기.

PDF 내부에서 자간(letter-spacing)이 크게 적용된 한글 텍스트가
한 글자씩 공백으로 분리된 상태로 추출되는 현상을 복원합니다.

    브 랜 드 운 영  →  브랜드운영
    전 세 계 누 적 바 이 어  →  전세계누적바이어

감지 조건:
    한글 1자(가-힣)인 토큰이 공백으로 분리되어 3개 이상 연속될 때

복원 방식:
    연속 구간의 공백을 모두 제거하여 붙여쓰기

복원 제외:
    - 영문 단독 (A B C D → 유지)
    - 숫자 단독 (1 2 3 4 → 유지)
    - 이미 정상적으로 띄어진 다음절 단어 (로그인 회원가입 → 유지)
    - 연속 2개 이하 (최소 3개 연속만 복원)

Kiwi 띄어쓰기 복원 (ENABLE_KIWI_SPACING):
    위 자간 복원과는 반대 방향 문제 - 단어 사이 공백이 아예 없는 경우를 고친다.
    ENABLE_KIWI_SPACING = True (기본값) 이면 자간 복원 이후 kiwipiepy로 띄어쓰기를 추가한다.
        시간대배포는원칙적으로금지하며 → 시간대 배포는 원칙적으로 금지하며
        브랜드운영 → 브랜드 운영
    Kiwi는 사전에 없는 전문 용어/합성어(예: "핫픽스")를 잘못 쪼갤 수 있어서,
    _USER_DICTIONARY에 그런 단어를 등록해서 오분석을 줄인다. 새로 깨지는 단어를
    발견하면 여기 추가하면 된다.
"""
from __future__ import annotations

import re

_SINGLE_KO = re.compile(r'^[가-힣]$')
_MIN_RUN = 3

# 멀티라인 복원: 짧은 줄(≤2자, 한글/영문만) + 다음 줄(≥5자, 한글 시작) → 병합
_SHORT_ONLY_KO_EN = re.compile(r'^[가-힣a-zA-Z]{1,2}$')

# ── Kiwi 띄어쓰기 옵션 ────────────────────────────────────────────────────────
ENABLE_KIWI_SPACING: bool = True

# Kiwi가 기본 사전에 없어서 잘못 쪼개는 사내/기술 용어들. (단어, 품사태그) 쌍.
# NNG = 일반명사. 새로 깨지는 사례를 발견하면 여기 추가.
_USER_DICTIONARY: list[tuple[str, str]] = [
    ("핫픽스", "NNG"),
]

_kiwi = None


def _get_kiwi():
    """Kiwi 인스턴스를 지연 초기화하고, 사용자 사전을 등록합니다."""
    global _kiwi
    if _kiwi is None:
        try:
            from kiwipiepy import Kiwi
        except ImportError:
            raise ImportError(
                "kiwipiepy가 설치되지 않았습니다.\n"
                "pip install kiwipiepy 로 설치하거나 "
                "ENABLE_KIWI_SPACING = False 로 설정하세요."
            )
        kiwi = Kiwi()
        for word, tag in _USER_DICTIONARY:
            kiwi.add_user_word(word, tag)
        _kiwi = kiwi
    return _kiwi


def restore_spacing(text: str) -> str:
    """자간 분리된 한글 텍스트를 복원합니다.

    ENABLE_KIWI_SPACING = True 이면 복원 후 Kiwi 띄어쓰기도 적용합니다.

    Args:
        text: 정제 전 텍스트 (개행 포함 가능)

    Returns:
        자간 분리가 복원된 텍스트
    """
    result = _restore_spacing_only(text)
    if ENABLE_KIWI_SPACING:
        result = apply_kiwi_spacing(result)
    return result


def _restore_spacing_only(text: str) -> str:
    """Kiwi 없이 자간 분리만 복원합니다 (내부용)."""
    lines = text.split('\n')
    return '\n'.join(_restore_line(line) for line in lines)


def apply_kiwi_spacing(text: str) -> str:
    """kiwipiepy로 단어 사이 띄어쓰기를 복원합니다.

    줄바꿈을 보존하며 줄 단위로 처리합니다.
    """
    kiwi = _get_kiwi()
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            result.append(kiwi.space(stripped))
        else:
            result.append(line)
    return '\n'.join(result)


def restore_multiline(text: str) -> str:
    """여러 줄에 걸쳐 단편화된 텍스트를 보수적으로 병합합니다.

    조건 (둘 다 충족 시에만 병합):
      - 현재 줄: 2글자 이하이고 한글 또는 영문자만 구성
      - 다음 줄: 5글자 이상이고 한글로 시작

    예: "장\\n매 출 성\\n5.6%)" → "장매 출 성\\n5.6%)"
    """
    lines = text.split('\n')
    if len(lines) < 2:
        return text

    result: list[str] = []
    i = 0
    while i < len(lines):
        current = lines[i]
        stripped = current.strip()

        next_stripped = lines[i + 1].strip() if i + 1 < len(lines) else ""
        next_starts_ko = bool(next_stripped) and '가' <= next_stripped[0] <= '힣'
        if (
            i + 1 < len(lines)
            and _SHORT_ONLY_KO_EN.match(stripped)
            and len(next_stripped) >= 5
            and next_starts_ko
        ):
            # 병합: 현재 줄을 다음 줄 앞에 붙임
            lines[i + 1] = stripped + lines[i + 1]
            i += 1
            continue

        result.append(current)
        i += 1

    return '\n'.join(result)


def _restore_line(line: str) -> str:
    """한 줄 내의 자간 분리 패턴을 복원합니다."""
    tokens = line.split(' ')
    result: list[str] = []
    i = 0

    while i < len(tokens):
        # 현재 위치부터 단일 한글 문자 토큰 연속 구간 탐색
        j = i
        while j < len(tokens) and _SINGLE_KO.match(tokens[j]):
            j += 1

        run_len = j - i

        if run_len >= _MIN_RUN:
            # 연속 한글 단글자 → 공백 없이 병합
            result.append(''.join(tokens[i:j]))
            i = j
        else:
            result.append(tokens[i])
            i += 1

    return ' '.join(result)
