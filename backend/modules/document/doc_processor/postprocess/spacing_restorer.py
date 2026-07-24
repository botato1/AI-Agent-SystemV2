"""자간 분리 텍스트 복원기.

PDF 내부에서 자간(letter-spacing)이 크게 적용된 한글 텍스트가
한 글자씩 공백으로 분리된 상태로 추출되는 현상을 복원합니다.

    브 랜 드 운 영  →  브랜드운영
    전 세 계 누 적 바 이 어  →  전세계누적바이어
"""
from __future__ import annotations

import re

_SINGLE_KO = re.compile(r'^[가-힣]$')
_MIN_RUN = 3

# 멀티라인 복원: 짧은 줄(≤2자, 한글/영문만) + 다음 줄(≥5자, 한글 시작) → 병합
_SHORT_ONLY_KO_EN = re.compile(r'^[가-힣a-zA-Z]{1,2}$')


def restore_spacing(text: str) -> str:
    lines = text.split('\n')
    return '\n'.join(_restore_line(line) for line in lines)


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
