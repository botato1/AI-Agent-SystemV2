"""spacing_restorer.py 회귀 테스트.

Kiwi 띄어쓰기 복원을 건드릴 때, 자간 복원(letter-spacing)이 여전히 잘 되는지 +
Kiwi가 사전에 없는 도메인 용어("핫픽스" 등)를 잘못 쪼개지 않는지 확인하기 위한 테스트.

실행 (backend/modules/document/ 에서): python -m doc_processor.postprocess.test_spacing_restorer_regression
"""

from doc_processor.postprocess.spacing_restorer import (
    _restore_spacing_only,
    restore_multiline,
    restore_spacing,
)


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    return condition


def main():
    results = []

    # ── 1. 자간 복원만 (Kiwi 제외) — 기존 docstring 예시 ──────────────────────
    results.append(check(
        "자간 분리 한글 복원: 브 랜 드 운 영 → 브랜드운영",
        _restore_spacing_only("브 랜 드 운 영") == "브랜드운영",
    ))
    results.append(check(
        "자간 분리 한글 복원: 전 세 계 누 적 바 이 어 → 전세계누적바이어",
        _restore_spacing_only("전 세 계 누 적 바 이 어") == "전세계누적바이어",
    ))
    results.append(check(
        "자간 분리 한글 복원: 자 기 자 본 이 익 률 → 자기자본이익률",
        _restore_spacing_only("자 기 자 본 이 익 률") == "자기자본이익률",
    ))
    results.append(check(
        "영문 단독은 복원 제외: A B C D 유지",
        _restore_spacing_only("A B C D") == "A B C D",
    ))
    results.append(check(
        "숫자 단독은 복원 제외: 1 2 3 4 유지",
        _restore_spacing_only("1 2 3 4") == "1 2 3 4",
    ))
    results.append(check(
        "이미 정상 띄어쓰기된 다음절 단어는 유지: 로그인 회원가입",
        _restore_spacing_only("로그인 회원가입") == "로그인 회원가입",
    ))
    results.append(check(
        "연속 2개 이하는 복원 안 함: 가 나 유지",
        _restore_spacing_only("가 나") == "가 나",
    ))

    # ── 2. 멀티라인 복원 ──────────────────────────────────────────────────────
    results.append(check(
        "멀티라인 복원: 장\\n매 출 성\\n5.6%) → 장매 출 성\\n5.6%)",
        restore_multiline("장\n매 출 성\n5.6%)") == "장매 출 성\n5.6%)",
    ))

    # ── 3. Kiwi 포함 전체 파이프라인 (restore_spacing, ENABLE_KIWI_SPACING=True) ──
    # 알림 메시지에서 실제로 발견된 깨진 사례 - 단어 사이 공백이 아예 없는 경우.
    results.append(check(
        "Kiwi 띄어쓰기: 시간대배포는원칙적으로금지하며 → 단어 사이 공백 생김",
        restore_spacing("그 외 요일/시간대배포는원칙적으로금지하며,")
        == "그 외 요일/ 시간대 배포는 원칙적으로 금지하며,",
    ))
    results.append(check(
        "Kiwi 띄어쓰기: 배포는매주화 요일 → 단어 경계 일부 복원",
        restore_spacing("배포는매주화 요일, 목요일 오후 2시에만 진행한다.")
        == "배포는 매주 화 요일, 목요일 오후 2시에만 진행한다.",
    ))
    # 사용자 사전 검증 - "핫픽스"가 "핫 픽스"로 잘못 쪼개지면 안 된다.
    results.append(check(
        "사용자 사전: 핫픽스는 그대로 유지 (핫 픽스로 안 쪼개짐)",
        "핫픽스" in restore_spacing("예외상황(장애 핫픽스 등)에만")
        and "핫 픽스" not in restore_spacing("예외상황(장애 핫픽스 등)에만"),
    ))
    # 이미 정상 문장은 Kiwi가 건드리면 안 된다.
    results.append(check(
        "정상 문장은 Kiwi가 그대로 둠",
        restore_spacing("API 게이트웨이는 하나로 통일하는 게 나을 것 같아요")
        == "API 게이트웨이는 하나로 통일하는 게 나을 것 같아요",
    ))
    # 자간 복원 + Kiwi가 순서대로 적용되는지 (letter-spaced 입력 → 붙인 뒤 → 다시 띄어씀)
    results.append(check(
        "자간 복원 → Kiwi 순서로 적용: 브 랜 드 운 영 → 브랜드 운영",
        restore_spacing("브 랜 드 운 영") == "브랜드 운영",
    ))

    print()
    total = len(results)
    passed = sum(results)
    print(f"{passed}/{total} passed")
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
