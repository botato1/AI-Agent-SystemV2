"""assembler.py 회귀 테스트.

새 PDF에서 문제를 고칠 때, 예전에 이미 고친 케이스들이
다시 깨지지 않았는지 확인하기 위한 테스트.

실행: python doc_processor/output/test_assembler_regression.py
"""

from doc_processor.output.assembler import (
    _chart_has_content,
    _title_is_valid,
    _dedupe_rows,
)


class FakeChart:
    def __init__(self, description, extracted_data=None):
        self.description = description
        self.extracted_data = extracted_data


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    return condition


def main():
    results = []

    # p7: 숫자 없는 레이블 테이블 (섹션 구분 페이지) -> 차트 아님
    chart_p7 = FakeChart("| 항목 | 값 |\n| --- | --- |\n| 이름 | 종류 |")
    results.append(check(
        "p7 숫자 없는 레이블 테이블은 차트로 인정 안 됨",
        _chart_has_content(chart_p7) is False,
    ))

    # p12: title이 없는 VL 환각 테이블 -> _build_charts에서 제외되어야 함 (title 자체 검증)
    results.append(check(
        "빈 title은 무효",
        _title_is_valid("") is False,
    ))

    # 순수 숫자 제목
    results.append(check(
        "순수 숫자 제목('-0.2')은 무효",
        _title_is_valid("-0.2") is False,
    ))

    # 출처 문구
    results.append(check(
        "출처 문구('자료:한국은행')는 무효",
        _title_is_valid("자료:한국은행") is False,
    ))

    # 새 PDF에서 나온 제네릭 제목들
    for generic in ["차트 데이터", "데이터", "데이터 표", "그래프", "표"]:
        results.append(check(
            f"제네릭 제목('{generic}')은 무효",
            _title_is_valid(generic) is False,
        ))

    # 정상 제목은 유효해야 함
    for valid in ["지역별 주택 매매가격 변동률", "주택담보대출 금리 추이", "부동산 PF 여신 잔액 및 연체율"]:
        results.append(check(
            f"정상 제목('{valid}')은 유효",
            _title_is_valid(valid) is True,
        ))
    
    # 괄호로만 된 축 단위 라벨은 전부 무효 (SK Research "(% WoW)" 케이스)
    for unit in ["(% WoW)", "(%)", "(pt)", "(단위: %)", "(원)", "(만호)"]:
        results.append(check(
            f"단위 라벨('{unit}')은 무효",
            _title_is_valid(unit) is False,
        ))

    # 헤더 중복 행 제거 (p6/p13에서 나온 패턴)
    rows_with_header_leak = [
        {"지역": "수도권", "변동률 (%/MoM)": "-0.2 ~ 0.8"},
        {"지역": "지역", "변동률 (%/MoM)": "변동률 (%/YoY)"},  # 헤더가 데이터로 섞임
        {"지역": "서울", "변동률 (%/MoM)": "-80 ~ 120"},
    ]
    deduped = _dedupe_rows(rows_with_header_leak)
    results.append(check(
        "헤더 중복 행 제거됨",
        len(deduped) == 2 and all(r["지역"] != "지역" for r in deduped),
    ))

    # 반복 환각 행 제거 (p12에서 60번 가까이 반복되던 패턴)
    rows_with_loop = [{"연도": "'22", "대출태도": -25, "대출수요": 15}] * 50
    rows_with_loop.insert(0, {"연도": "'20", "대출태도": 9, "대출수요": 7})
    deduped_loop = _dedupe_rows(rows_with_loop)
    results.append(check(
        "반복 환각 행이 1개로 정리됨",
        len(deduped_loop) == 2,
    ))

    print()
    total = len(results)
    passed = sum(results)
    print(f"{passed}/{total} passed")
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
