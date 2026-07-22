"""실시간 판단 파이프라인 1-4: 팝업 우선순위 및 동시 발생 처리

한 발화에서 decision_judgment(1-1)와 document_judgment(1-2)가 동시에 조건을
만족할 수 있다. 발화당 팝업은 최대 1개만 - 우선순위 고정 (설계 문서 1-4 규칙 B).

1순위: 1-1 Case 3 (decision 대비 모순)
2순위: 1-2 모순 (문서 대비 모순)
3순위: 1-1 Case 0 (결정 리마인더)
4순위: 1-1 Case 4 (반복 논의 알림)
5순위: 1-2 문서 추천
"""

_PRIORITY_ORDER = [
    ("decision_judgment", "3"),   # 1순위: decision 대비 모순
    ("document_judgment", "contradiction"),  # 2순위: 문서 대비 모순
    ("decision_judgment", "0"),   # 3순위: 결정 리마인더
    ("decision_judgment", "4"),   # 4순위: 반복 논의 알림
    ("document_judgment", "recommendation"),  # 5순위: 문서 추천
]


def select_popup(decision_result: dict, document_result: dict | None) -> dict | None:
    """
    decision_judgment.judge()와 document_judgment.judge()의 결과를 받아,
    우선순위가 가장 높은 팝업 하나만 골라 반환한다. 둘 다 팝업이 없으면 None.

    Args:
        decision_result: decision_judgment.judge()의 반환값
        document_result: document_judgment.judge()의 반환값. decision_result["case"]가
                          "none"이 아니면(=DECISION_COLLECTION에서 매칭됐으면) document_judgment는
                          아예 호출 안 됐을 수 있으므로 None 허용.
    """
    candidates = {
        ("decision_judgment", decision_result.get("case")): decision_result.get("popup"),
    }
    if document_result:
        candidates[("document_judgment", document_result.get("case"))] = document_result.get("popup")

    for key in _PRIORITY_ORDER:
        popup = candidates.get(key)
        if popup:
            return popup

    return None