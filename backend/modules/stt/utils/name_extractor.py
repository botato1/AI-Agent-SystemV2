import re

# "안녕하세요 이준오입니다" 류의 자기소개 문장에서 이름만 뽑아내는 패턴들.
# 위에서부터 순서대로 시도하고, 하나라도 맞으면 그 결과를 씀 (엄격한 패턴 → 느슨한 패턴 순).
_NAME_PATTERNS = [
    re.compile(r"안녕하세요[,.\s]*([가-힣]{2,10})\s*입니다"),
    re.compile(r"안녕하세요[,.\s]*([가-힣]{2,10})\s*이에요"),
    re.compile(r"안녕하세요[,.\s]*([가-힣]{2,10})\s*예요"),
    # "안녕하세요" 자체가 STT에서 인식이 안 됐을 때를 대비한 폴백
    re.compile(r"([가-힣]{2,10})\s*입니다"),
    re.compile(r"([가-힣]{2,10})\s*이에요"),
]


def extract_name_from_greeting(text: str) -> str | None:
    """
    "안녕하세요 이준오입니다" 같은 자기소개 문장에서 이름 부분만 추출.
    어떤 패턴에도 안 맞으면 None (호출부에서 수동 입력으로 폴백해야 함).
    """
    text = text.strip()
    for pattern in _NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None
