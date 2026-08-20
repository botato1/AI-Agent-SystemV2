"""text_parser.py 회귀 테스트.

PyMuPDF는 폰트가 바뀌는 지점마다(실제 글자 간격이 0이거나 겹쳐도) span을
나누는 경우가 있는데, 기존 코드는 span 사이를 무조건 공백으로 합쳐서
없던 공백이 생기는 버그가 있었다 (assembly_minutes_p27_28.pdf에서 실제 발견:
"많은생각이오고갑니다" → "많은생 각 이오고 갑 니다"). span 사이 실제
x좌표 간격이 있을 때만 공백을 넣도록 고친 뒤의 회귀 테스트.

실행 (backend/modules/document/ 에서): python -m doc_processor.parsers.test_text_parser_regression
"""

from doc_processor.parsers.text_parser import _join_spans


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    return condition


def span(text, x0, x1):
    return {"text": text, "bbox": [x0, 0.0, x1, 10.0]}


def main():
    results = []

    # ── 실제 회귀 재현: assembly_minutes_p27_28.pdf 실제 span 좌표 ───────────
    spans = [
        span("회의원무제한토론입니다.", 62.40, 197.21),
        span(" ", 197.21, 202.92),
        span("많은생", 202.92, 243.12),
        span("각", 243.12, 254.64),
        span("이오고", 254.52, 294.72),
        span("갑", 300.48, 311.99),
        span("니다.", 311.88, 337.73),
    ]
    # 간격이 0 이하(맞닿음/겹침)인 3곳은 고쳐지지만, "이오고"→"갑" 사이는
    # 실제 양수 간격(5.76pt)이라 이 보수적인 규칙으로는 못 잡는다 — 임계값을
    # 더 키우면 다른 문서의 진짜 단어 사이 공백까지 지울 위험이 있어 일부러
    # 안전한 쪽(0 이하만)으로 제한했다. 알려진 한계로 남겨둔다.
    results.append(check(
        "실제 회귀 재현: 간격 0 이하인 스퓨리어스 공백 3곳 제거 (양수 간격 1곳은 알려진 한계)",
        _join_spans(spans) == "회의원무제한토론입니다. 많은생각이오고 갑니다.",
    ))

    # ── 진짜 공백이 있는 정상 케이스는 그대로 유지 ───────────────────────────
    spans2 = [
        span("Hello", 0, 30),
        span("World", 35, 65),  # gap=5, 정상적인 단어 사이 공백
    ]
    results.append(check(
        "정상적인 단어 사이 공백(양수 간격)은 그대로 유지",
        _join_spans(spans2) == "Hello World",
    ))

    # ── 맞닿은 span(간격 0)은 공백 없이 붙임 ─────────────────────────────────
    spans3 = [
        span("abc", 0, 10),
        span("def", 10, 20),  # gap=0
    ]
    results.append(check(
        "간격 0인 span은 공백 없이 붙임",
        _join_spans(spans3) == "abcdef",
    ))

    # ── 겹치는 span(음수 간격)도 공백 없이 붙임 ──────────────────────────────
    spans4 = [
        span("abc", 0, 10),
        span("def", 9, 20),  # gap=-1 (겹침)
    ]
    results.append(check(
        "겹치는(음수 간격) span도 공백 없이 붙임",
        _join_spans(spans4) == "abcdef",
    ))

    # ── bbox 없는 span도 안전하게 처리 ───────────────────────────────────────
    spans5 = [{"text": "abc"}, {"text": "def"}]
    results.append(check(
        "bbox 없는 span: 예외 없이 처리 (공백 없이 이어붙임)",
        _join_spans(spans5) == "abcdef",
    ))

    # ── 빈 텍스트 span은 건너뜀 ──────────────────────────────────────────────
    spans6 = [span("abc", 0, 10), span("  ", 10, 15), span("def", 20, 30)]
    results.append(check(
        "공백뿐인 span은 건너뛰고, 이후 실제 간격으로 판단",
        _join_spans(spans6) == "abc def",
    ))

    print(f"\n{sum(results)}/{len(results)} passed")
    return all(results)


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
