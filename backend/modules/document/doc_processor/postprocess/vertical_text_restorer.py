"""세로 텍스트 복원기.

PaddleOCR가 세로 텍스트를 한 글자씩 줄바꿈으로 인식한 경우를 감지하고
가로 방향 문자열로 복원합니다.

감지 패턴:
    한글 1~2자 / 영문 1~2자로만 구성된 라인이 3줄 이상 연속될 때

복원 방식:
    - 한글: 공백 없이 붙여쓰기 (전세계누적바이어)
    - 영문: 공백으로 이어 붙이기 (Global Buyers)

제외:
    - 숫자 단독 라인
    - 표 데이터 (쉼표·| 포함 라인)
"""
from __future__ import annotations

import re

# 세로 텍스트로 판단할 라인 패턴
# 한글 1~2자 또는 영문 알파벳 1~2자 (숫자 단독 제외)
_KO_CHAR  = re.compile(r'^[ㄱ-ㆎ가-힣]{1,2}$')
_EN_CHAR  = re.compile(r'^[a-zA-Z]{1,2}$')

# 세로 텍스트로 확신하기 위한 최소 연속 줄 수
_MIN_SEQ  = 3

# 이 패턴이 있는 라인은 표 데이터 → 복원 대상 제외
_TABLE_HINT = re.compile(r'[,|;\t]')


def _is_vertical_line(line: str) -> tuple[bool, str]:
    """라인이 세로 텍스트 한 줄인지 판단합니다.

    Returns:
        (is_vertical, lang)  lang = "ko" | "en" | ""
    """
    stripped = line.strip()
    if not stripped:
        return False, ""
    if _TABLE_HINT.search(stripped):
        return False, ""
    if _KO_CHAR.match(stripped):
        return True, "ko"
    if _EN_CHAR.match(stripped):
        return True, "en"
    return False, ""


def restore_vertical_text(text: str) -> str:
    """세로 텍스트가 포함된 문자열에서 연속 패턴을 감지하고 복원합니다.

    Args:
        text: OCR 결과 텍스트 (개행 포함)

    Returns:
        복원된 텍스트
    """
    lines = text.split('\n')
    result: list[str] = []
    i = 0

    while i < len(lines):
        # 현재 위치부터 연속 세로 라인 수집
        seq: list[str]  = []
        langs: list[str] = []
        j = i

        while j < len(lines):
            ok, lang = _is_vertical_line(lines[j])
            if ok:
                seq.append(lines[j].strip())
                langs.append(lang)
                j += 1
            else:
                break

        if len(seq) >= _MIN_SEQ:
            # 언어 판정: 과반수 언어 사용
            ko_count = langs.count("ko")
            sep = "" if ko_count >= len(langs) / 2 else " "
            restored = sep.join(seq)
            result.append(restored)
            i = j
        else:
            # 세로 텍스트 아님 — 원본 유지
            result.append(lines[i])
            i += 1

    return '\n'.join(result)
