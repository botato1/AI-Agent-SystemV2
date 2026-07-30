"""
한국어 수사 → 아라비아 숫자 변환 (ITN, inverse text normalization).

왜 필요한가:
  Qwen3-ASR은 숫자를 들리는 대로 쓴다 — "8002번 포트"를 "팔천이번 포트"로,
  "45%"를 "사십오 퍼센트"로 출력한다. 인식은 정확한데 표기만 다르다.
  회의록에서 포트 번호·버전·날짜는 모순 감지가 직접 비교하는 값이라 숫자 형태여야 한다.
  (컨텍스트에 "숫자는 아라비아 숫자로 표기" 지시문을 넣는 방법은 실측 무효 확인 —
   Qwen 컨텍스트 바이어싱은 어휘에만 작동하고 출력 형식은 제어하지 못한다.)

설계 원칙 — **확신할 때만 변환한다.**
  한국어는 수사와 일반 단어의 음절이 겹친다. "이번"(this time)을 "2번"으로,
  "일단"(first of all)을 "1단"으로 바꾸면 안 바꾼 것보다 나쁘다. 그래서
  **수사 뒤에 단위/조수사가 붙은 경우만** 변환한다.
    변환   "팔천이번" → "8002번"   ("번"이 단위)
    변환   "구십사년" → "94년"
    미변환 "하나 둘"              (단위 없음 — 놓치지만 안전)
    미변환 "이번에는"             (_STOPWORDS로 명시 차단)
  놓치는 건 회수 가능하지만 망친 건 회수가 안 된다.
"""
import re

# ── 한자어 수사 ──────────────────────────────────────────
_SINO_DIGIT = {"영": 0, "공": 0, "일": 1, "이": 2, "삼": 3, "사": 4,
               "오": 5, "육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9}
_SINO_UNIT = {"십": 10, "백": 100, "천": 1000}
_SINO_BIG = {"만": 10 ** 4, "억": 10 ** 8, "조": 10 ** 12}
_SINO_CHARS = "".join(list(_SINO_DIGIT) + list(_SINO_UNIT) + list(_SINO_BIG))

# ── 고유어 수사 ──────────────────────────────────────────
# 관형사형(한/두/세/네, 스무)은 조수사 앞에서 쓰이는 형태라 함께 넣는다.
_NATIVE_TENS = {"열": 10, "스물": 20, "스무": 20, "서른": 30, "마흔": 40, "쉰": 50,
                "예순": 60, "일흔": 70, "여든": 80, "아흔": 90}
_NATIVE_ONES = {"하나": 1, "한": 1, "둘": 2, "두": 2, "셋": 3, "세": 3, "넷": 4, "네": 4,
                "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}

# ── 단위/조수사 ──────────────────────────────────────────
# 이 목록에 있는 단위가 수사 바로 뒤에 붙어야 변환한다. 긴 것을 먼저 둬야
# 정규식 대안(|)이 "개월"을 "개"로 잘라먹지 않는다.
_COUNTERS = [
    "개월", "시간", "퍼센트", "프로", "인분", "인당", "번째", "가지", "군데", "자리",
    "밀리초", "킬로", "미터", "기가", "메가", "바이트", "달러", "엔",
    "시", "분", "초", "개", "명", "번", "배", "장", "권", "년", "월", "일", "원",
    "층", "대", "살", "마리", "병", "잔", "차", "회", "판", "줄", "칸", "쪽", "위",
]
_COUNTER_RE = "|".join(_COUNTERS)

# ── 오변환 차단 목록 ────────────────────────────────────
# 수사 + 단위 형태를 갖췄지만 실제로는 숫자가 아닌 표현들.
# 변환 후보 문자열 전체(수사+단위)가 여기 있으면 건드리지 않는다.
# 실사용 오변환이 발견되면 여기에 추가하는 것이 1차 대응이다.
_STOPWORDS = {
    "이번", "저번", "이월", "이번째",   # 이번에는 / 저번에 / 이월하다
    "일단", "일일", "일회", "일위",     # 일단은 / 일일이 / 일회용
    "사시", "사장", "사원", "사회", "사시간",   # 사장님 / 사회적
    "오시", "오분",                    # "오시는 길"의 오시
    "칠판", "칠회",
    "구시", "구위",
    "한번", "한판", "한잔", "한대", "한자리", "한층", "한번째",
    "두루", "세월", "세대", "네일",
    "십분",                           # "십분 이해한다" 관용구
    "만원", "만일", "만회", "만년",
    "백일", "백번",                    # 백일몽 / 백번 말해도
}


def _parse_sino(text: str) -> int | None:
    """한자어 수사 문자열을 정수로. 팔천이→8002, 구십사→94, 십육→16."""
    total = section = digit = 0
    seen = False
    for ch in text:
        if ch in _SINO_DIGIT:
            digit = _SINO_DIGIT[ch]
            seen = True
        elif ch in _SINO_UNIT:
            # "십"처럼 앞자리가 없으면 1로 본다 (십육 = 16)
            section += (digit or 1) * _SINO_UNIT[ch]
            digit = 0
            seen = True
        elif ch in _SINO_BIG:
            section += digit
            total += (section or 1) * _SINO_BIG[ch]
            section = digit = 0
            seen = True
        else:
            return None
    return total + section + digit if seen else None


def _parse_native(text: str) -> int | None:
    """고유어 수사 문자열을 정수로. 열다섯→15, 스물셋→23, 두→2."""
    value = 0
    rest = text
    for tens, n in sorted(_NATIVE_TENS.items(), key=lambda kv: -len(kv[0])):
        if rest.startswith(tens):
            value += n
            rest = rest[len(tens):]
            break
    if rest:
        for ones, n in sorted(_NATIVE_ONES.items(), key=lambda kv: -len(kv[0])):
            if rest == ones:
                value += n
                rest = ""
                break
    return value if (value and not rest) else None


_NATIVE_ALL = sorted(list(_NATIVE_TENS) + list(_NATIVE_ONES), key=len, reverse=True)
_NATIVE_WORD = "|".join(_NATIVE_ALL)

# 수사 + 단위. 앞에 한글 음절이 이어지면(=더 긴 단어의 일부) 매칭하지 않는다.
#
# 단위 뒤에는 한글을 허용해야 한다 — 한국어는 조사가 항상 붙기 때문에
# ("구십사년보다", "아홉 시에", "스물세 명이") 뒤를 막으면 실제 문장에서 대부분
# 놓친다. 대신 그 때문에 생기는 오변환("사장"→"4장", "칠판"→"7판")은
# _STOPWORDS로 막는다. 새 오변환이 발견되면 그쪽에 추가하는 게 1차 대응.
_PATTERN = re.compile(
    rf"(?<![가-힣])"
    rf"(?P<num>[{_SINO_CHARS}]+|(?:{_NATIVE_WORD})(?:{_NATIVE_WORD})?)"
    rf"\s?(?P<counter>{_COUNTER_RE})"
)

# "십육 점 팔" → 16.8. 소수점은 단위 없이도 등장하므로 별도로 먼저 처리한다.
_DECIMAL = re.compile(
    rf"(?<![가-힣])(?P<int>[{_SINO_CHARS}]+)\s*점\s*(?P<frac>(?:[{_SINO_CHARS}]\s*)+)(?![가-힣])"
)


def _sub_decimal(m: re.Match) -> str:
    whole = _parse_sino(m.group("int"))
    digits = [_SINO_DIGIT.get(ch) for ch in m.group("frac") if ch.strip()]
    if whole is None or not digits or any(d is None for d in digits):
        return m.group(0)
    return f"{whole}.{''.join(str(d) for d in digits)}"


def _sub_counted(m: re.Match) -> str:
    if m.group(0).replace(" ", "") in _STOPWORDS:
        return m.group(0)
    num = m.group("num")
    value = _parse_sino(num) if all(c in _SINO_CHARS for c in num) else _parse_native(num)
    if value is None:
        return m.group(0)
    return f"{value}{m.group('counter')}"


def to_digits(text: str) -> str:
    """
    한국어 수사를 아라비아 숫자로. 확신할 수 없는 부분은 원문 그대로 남긴다.

    >>> to_digits("서버 팔천이번 포트에서")
    '서버 8002번 포트에서'
    >>> to_digits("무려 사십오 퍼센트")
    '무려 45퍼센트'
    >>> to_digits("이번에는 안 돼")
    '이번에는 안 돼'
    """
    if not text:
        return text
    text = _DECIMAL.sub(_sub_decimal, text)
    return _PATTERN.sub(_sub_counted, text)
