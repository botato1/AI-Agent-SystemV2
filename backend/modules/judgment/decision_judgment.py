"""실시간 판단 파이프라인 1-1: 결정 비교 판단 (통합)

결정 리마인더 / 근거 명확한 변경 / 근거 불명확한 변경, 이 세 기능은 별개가 아니라
하나의 판단 파이프라인이 결과에 따라 갈라진 것이다 (설계 문서 1-1 참조).

핵심 원칙 — "이미 결정된 걸 다르게 말하는 것 = 변경 후보":
발화가 새로운 값/입장을 제시하는가(→ 값 비교로), 아니면 주제만 재언급하는가
(→ 리마인더)를 먼저 가른다. 재확인이 "글자 그대로 같을 때만"으로 좁아지는 걸
피하기 위함.

3단계 판단 (전부 Model1 단일 파인튜닝 모델을 배치별 instruction으로 순차 호출):
  1단계) 새 값 제시 여부   → 아니오: Case 0(리마인더)
  2단계) 값이 기존과 같은가 → 예: Case 1(무시)
  3단계) 근거가 명확한가   → 예: Case 2(명확한 근거의 변경) / 아니오: Case 3(명확한 근거 없이 변경)

[수정 - 2026.07.27] confidence/Model2 이원화 및 Case 4(보류·반복카운트) 제거.
Case 4는 세션 카운트 기반으로 재설계해서 별도로 다시 넣을 예정 - 지금은 없음.

[수정] 카테고리 내 active decision 전체를 topic_match로 판단하던 것(벡터 검색
완전 제거)을 되돌림 - decision이 쌓일수록 발화 1개당 LLM 호출이 선형으로 늘어나
느려지는 문제가 있었음. 벡터 검색을 "필터"가 아니라 "후보 축소"로만 앞단에 둔다
(임계값을 낮게 잡아 진짜 매칭이 후보 밖으로 밀리는 걸 방지, 최종 판단은 여전히
topic_match가 함).

[수정] Case 2/3는 "모순"이 아니라 "결정 변경"으로 명명한다 - 문서 내용과의
충돌(document_judgment)과는 성격이 달라, 근거 명확성 기준으로
reasoned_change/unreasoned_change로 구분한다. 팝업은 세션 내 (decision, case)
단위로 1회만 뜨지만, contradictions row는 매번 생성되어 post-meeting이 세션 내
최신 행을 그대로 사용자 확인 대상으로 재사용할 수 있게 한다 (전체 회의를 다시
읽고 재판단하지 않음 - decision_transition.py 참조).
"""

import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.crud import contradiction_crud, history_crud
from backend.db.modules import Decision, Meeting
from backend.modules.llm.ollama_client import _call_ollama
from backend.modules.rag import chroma_client

# [수정 - 2026.07.27] confidence/Model2 이원화 제거. 판단은 배치1~4 통합
# 파인튜닝 모델(re-call-model1-unified-v7) 하나로, 단계별 개별 호출.
# ollama_client.OLLAMA_MODEL_LIGHT를 그대로 안 쓰는 이유: 그건 의도분류/일반답변
# 등 다른 기능도 같이 쓰는 공용 상수라, 판단 전용 모델을 거기 넣으면 다른 기능까지
# 좁은 판단용 모델로 넘어가게 됨 - 판단 파이프라인 전용 상수를 따로 둔다.
JUDGMENT_MODEL = os.getenv("OLLAMA_MODEL_JUDGMENT", "re-call-model1-unified-v7")

# [수정 - 2026.08.03] threshold=0.3은 실회의록 스모크테스트(data/test_meetings/)에서
# 결정 개수가 적은 워크스페이스일 때 "넵 알겠습니다" 같은 무관한 발화까지 거의 항상
# 후보로 통과시키는 것을 확인함(dense count == final count로 사실상 무필터). 후보
# narrowing이 안 되면 topic_match 잔여 오류율(홀드아웃 기준 8~10%)이 후보 개수만큼
# 곱해져 노출됨 - 0.5로 올려 실제 필터 역할을 하게 함(TBD - 추후 대규모 실측 후 재조정).
DECISION_CANDIDATE_TOP_K = int(os.getenv("DECISION_CANDIDATE_TOP_K", "15"))
DECISION_CANDIDATE_THRESHOLD = float(os.getenv("DECISION_CANDIDATE_THRESHOLD", "0.5"))

# [수정 - 리뷰 반영] 벡터 후보(top-15)를 전부 topic_match로 순회하면 무관한 발화 하나당
# 최악의 경우 LLM 호출이 15번까지 순차로 늘어나 체감 지연이 커짐. 후보는 이미 벡터
# 점수 순 정렬이므로, 상위 몇 개까지만 topic_match로 확인하고 그 안에서 못 찾으면
# "none"으로 처리한다 (TBD - 실측 후 조정).
TOPIC_MATCH_MAX_ATTEMPTS = int(os.getenv("TOPIC_MATCH_MAX_ATTEMPTS", "5"))

# 배치1~3 학습 때 쓴 instruction 그대로 - 문구가 조금이라도 다르면 정확도가 크게 떨어짐
JUDGMENT_STEP_INSTRUCTIONS = {
    "presents_new_value": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화가 새로운 값/입장을 제시하는지, "
        "아니면 단순히 과거 결정을 재언급/질문하는 것인지만 판단해서 JSON으로만 답하라."
    ),
    "same_as_existing": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화는 이미 새로운 값/입장을 제시하고 있다. "
        "그 값이 기존 결정과 실질적으로 같은 내용인지 다른 내용인지만 판단해서 JSON으로만 답하라."
    ),
    "reason_is_clear": (
        "아래는 회의/채팅에서 방금 나온 발화이다. 이 발화는 이미 기존 결정과 다른 새 값을 제시하고 있다. "
        "왜 바뀌는지 근거/이유가 발화 안에 명확하게 드러나 있는지만 판단해서 JSON으로만 답하라."
    ),
}

JUDGMENT_INPUT_TEMPLATE = """[과거 결정]
{decision_text}
(결정 이유: {decision_reason})

[방금 발화]
{statement}"""

# 배치4(topic_match) v7 학습 때 쓴 instruction 그대로 - 문구가 조금이라도
# 다르면 정확도가 크게 떨어짐 (finetune/dataset_topic_match_v2_augment.jsonl 참조).
# 학습 데이터의 instruction 필드는 JSON 출력 스펙까지 안에 포함돼 있으므로,
# 이 상수도 스펙을 끝에 그대로 포함해서 학습 형식과 완전히 동일하게 맞춘다
# (아래 _ask_topic_match()에서 별도로 스펙을 덧붙이지 않는 이유이기도 함).
TOPIC_MATCH_INSTRUCTION = (
    "아래는 과거 의사결정과 새 발화이다.\n\n"
    "목표:\n새 발화가 과거 의사결정에서 실제로 결정된 그 항목·속성을 다루는지 판단하라.\n\n"
    "같은 주제(true)인 경우\n"
    "- 과거 의사결정에서 선택한 항목을 다른 기술/서비스/제품으로 교체하자는 제안\n"
    "- 과거 의사결정에서 정한 그 설정값(수치, 기간, 비율, 개수 등)을 조정하자는 제안\n"
    "- 과거 의사결정과 동일한 선택지를 놓고 대안을 비교하거나 장단점을 논하는 경우\n"
    "- 과거 의사결정 내용 자체를 단순히 되묻거나 재확인하거나 다시 언급하는 경우, "
    "변경 의도가 없는 동의·긍정적 코멘트도 포함\n"
    "  (예: \"그거 A로 하기로 했었죠?\", \"왜 A로 정했었죠\", \"A 맞나요\", "
    "\"A로 그대로 가면 될 것 같아요\", \"A가 요즘 보니 괜찮더라고요\")\n\n"
    "다른 주제(false)인 경우\n"
    "- 같은 시스템/프로젝트/컴포넌트에 대한 이야기라도, 과거 의사결정이 실제로\n"
    "  다루지 않은 별개의 속성·정책·운영 이슈인 경우\n"
    "  (예: \"DB는 PostgreSQL을 쓴다\"는 \"어떤 DB 기술을 쓸지\"에 대한 결정이므로,\n"
    "  같은 DB에 대한 이야기여도 \"백업 주기\", \"마이그레이션 자동화\" 등은 별개 항목)\n"
    "- 비슷한 분야/카테고리라도 역할이 다른 경우 (예: 관계형DB vs 벡터DB, "
    "인증 vs 권한관리, 캐시 vs 메시지큐, 검색엔진 vs 그래프DB) — 배경지식으로 "
    "역할이 다름을 판단해야 하는 경우도 포함\n"
    "- 기존 결정과 독립적인 신규 기능 또는 신규 컴포넌트 제안\n"
    "- 완전히 무관한 화제\n\n"
    "판단의 핵심은 \"같은 시스템/키워드가 언급되었는가\"가 아니라\n"
    "\"과거에 실제로 결정된 바로 그 속성을 다루는가\"이다.\n\n"
    "다음 JSON만 출력한다.\n{\n  \"reason\": \"20자 이내\",\n  \"same_topic\": true | false\n}"
)

TOPIC_MATCH_INPUT_TEMPLATE = """[과거 의사결정]
{decision_text}
(결정 이유: {decision_reason})

[새 발화]
{statement}"""


def _ask_judgment_step(key: str, decision_text: str, decision_reason: str, statement: str) -> bool:
    """JUDGMENT_MODEL에게 단계 하나(key)만 물어서 bool로 반환. 실패 시 False."""
    input_text = JUDGMENT_INPUT_TEMPLATE.format(
        decision_text=decision_text, decision_reason=decision_reason, statement=statement,
    )
    prompt = (
        f"{JUDGMENT_STEP_INSTRUCTIONS[key]}\n\n{input_text}\n\n"
        f'반드시 다음 JSON 형식으로만 답하라 (다른 설명 금지):\n{{\n  "{key}": true/false\n}}'
    )
    raw = _call_ollama(prompt, timeout=60.0, model=JUDGMENT_MODEL)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return False
        parsed = json.loads(raw[start : end + 1])
        return bool(parsed.get(key, False))
    except (json.JSONDecodeError, ValueError):
        return False


def _ask_topic_match(decision_text: str, decision_reason: str, statement: str) -> bool:
    """후보 decision과 발화가 실제로 같은 의사결정을 수정하려는 건지 topic_match로 검증."""
    input_text = TOPIC_MATCH_INPUT_TEMPLATE.format(
        decision_text=decision_text, decision_reason=decision_reason, statement=statement,
    )
    # TOPIC_MATCH_INSTRUCTION이 이미 JSON 출력 스펙을 끝에 포함하고 있으므로
    # (학습 데이터의 instruction 필드와 동일한 형식), 여기서 별도로 스펙을
    # 덧붙이지 않는다 - instruction 뒤에 input만 붙이는 게 학습 형식과 일치한다.
    prompt = f"{TOPIC_MATCH_INSTRUCTION}\n\n{input_text}"
    raw = _call_ollama(prompt, timeout=60.0, model=JUDGMENT_MODEL)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return False
        parsed = json.loads(raw[start : end + 1])
        return bool(parsed.get("same_topic", False))
    except (json.JSONDecodeError, ValueError):
        return False


def _get_candidate_decisions(
    db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, statement: str
) -> list[Decision]:
    """벡터 검색으로 후보를 먼저 좁힌 뒤, topic_match는 그 후보에 대해서만 돈다.
    [수정] active decision 전체를 매번 topic_match하면 decision이 쌓일수록
    발화 1개당 LLM 호출이 선형으로 늘어 느려짐 - 벡터 검색을 "필터"가 아니라
    "후보 축소"용으로 다시 앞단에 둔다. threshold를 낮게 잡아 임베딩이 약한
    진짜 매칭도 후보에서 안 빠지게 한다. Decision엔 category_id가 없어
    Meeting을 조인한다."""
    results = chroma_client.search_hybrid(
        query_text=statement,
        workspace_id=str(workspace_id),
        category_id=str(category_id),
        top_k=DECISION_CANDIDATE_TOP_K,
        collection_name=chroma_client.DECISION_COLLECTION,
    )
    candidate_ids = [
        uuid.UUID(r["document_id"]) for r in results
        if r.get("document_id") and r["score"] >= DECISION_CANDIDATE_THRESHOLD
    ]
    if not candidate_ids:
        return []

    decisions = (
        db.query(Decision)
        .join(Meeting, Decision.meeting_id == Meeting.id)
        .filter(
            Decision.id.in_(candidate_ids),
            Meeting.category_id == category_id,
            Decision.workspace_id == workspace_id,
            Decision.status == "active",
            Decision.deleted_at.is_(None),
        )
        .all()
    )
    order = {cid: i for i, cid in enumerate(candidate_ids)}
    decisions.sort(key=lambda d: order.get(d.id, len(order)))  # 벡터 점수 순서 유지
    return decisions


def judge(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    source_type: str,  # 'meeting_segment' | 'room_message'
    source_id: uuid.UUID,
    statement: str,
    session_meeting_id: uuid.UUID | None = None,
    session_room_id: uuid.UUID | None = None,
) -> dict:
    """
    발화 하나를 받아 1-1 판단을 수행한다.

    Returns:
        {"case": "none"|"0"|"1"|"2"|"3", "popup": dict|None, "decision_id": str|None}
        popup은 팝업을 띄워야 하면 {"type": ..., "message": ...} 형태, 아니면 None.
        "none"은 관련 있는 active decision이 없어 1-2로 넘겨야 함을 의미.
    """
    candidates = _get_candidate_decisions(db, workspace_id, category_id, statement)

    decision = None
    for candidate in candidates[:TOPIC_MATCH_MAX_ATTEMPTS]:
        if _ask_topic_match(candidate.decision_text, candidate.reason or "명시되지 않음", statement):
            decision = candidate
            break

    if decision is None:
        return {"case": "none", "popup": None, "decision_id": None}

    decision_text = decision.decision_text
    decision_reason = decision.reason or "명시되지 않음"
    session_kwargs = {"session_meeting_id": session_meeting_id, "session_room_id": session_room_id}

    # 1단계: 새 값 제시 여부
    presents_new_value = _ask_judgment_step("presents_new_value", decision_text, decision_reason, statement)

    if not presents_new_value:
        # Case 0: 리마인더 - 세션당 1회
        already_shown = history_crud.already_notified_in_session(
            db, reference_decision_id=decision.id, **session_kwargs
        )
        if already_shown:
            return {"case": "0", "popup": None, "decision_id": str(decision.id)}

        history_crud.record_match(
            db,
            workspace_id=workspace_id, category_id=category_id,
            source_type=source_type, match_type="decision_reminder",
            reference_decision_id=decision.id,
            confidence_score=1.0,  # 벡터 점수 대신 topic_match가 이미 같은 주제로 확정한 것이라 고정값
            **session_kwargs,
        )
        return {
            "case": "0",
            "popup": {
                "type": "decision_reminder",
                "message": f"이미 '{decision.decision_text}'로 결정된 이력이 있습니다"
                           f" ({decision.decided_at}, {decision.reason or '사유 미기재'})",
            },
            "decision_id": str(decision.id),
        }

    # 2단계: 값이 같은가?
    same_as_existing = _ask_judgment_step("same_as_existing", decision_text, decision_reason, statement)

    if same_as_existing:
        # Case 1: 팝업 없음
        return {"case": "1", "popup": None, "decision_id": str(decision.id)}

    # 3단계: 근거가 명확한가?
    reason_is_clear = _ask_judgment_step("reason_is_clear", decision_text, decision_reason, statement)

    # Case 2/3: "모순"이 아니라 근거 명확성 기준의 "결정 변경"으로 구분한다.
    # 실제 decisions 반영은 여전히 post-meeting이 담당 - 여기선 알림 + 기록만 한다.
    if reason_is_clear:
        case, judgment_case = "2", "reasoned_change"
        message = (f"근거가 확인되어 결정이 바뀐 것으로 보입니다: '{statement}'"
                   f" (기존: {decision.decided_at}에 결정된 '{decision.decision_text}')."
                   f" 바꾸시겠습니까?")
    else:
        case, judgment_case = "3", "unreasoned_change"
        message = (f"명확한 근거 없이 결정이 바뀐 것으로 보입니다: '{statement}'"
                   f" (기존: {decision.decided_at}에 결정된 '{decision.decision_text}')."
                   f" 바꾸시겠습니까?")

    # 팝업은 세션 내 (decision, judgment_case) 단위로 1회만 - 같은 decision이어도
    # 근거 명확/불명확 여부가 바뀌면 별개 알림으로 취급해 각각 1회씩 뜬다.
    already_popped = contradiction_crud.already_popped_in_session_for_decision(
        db, reference_decision_id=decision.id, judgment_case=judgment_case, **session_kwargs
    )

    # make_deduplication_key의 3번째 인자명이 reference_file_id지만, decision 참조도
    # 같은 함수로 dedup key를 만들 수 있어 재사용 (해시 조합용이라 의미상 문제 없음)
    dedup_key = contradiction_crud.make_deduplication_key(
        source_type, source_id, decision.id, decision.id
    )
    # 팝업 노출 여부와 무관하게 매번 기록 - post-meeting이 세션 내 이 decision의
    # 최신 행을 그대로 사용자 확인 대상(변경 후보)으로 재사용한다.
    contradiction = contradiction_crud.create_contradiction(
        db,
        workspace_id=workspace_id, category_id=category_id,
        source_type=source_type, reference_type="decision",
        reference_decision_id=decision.id,
        statement_text_snapshot=statement,
        reference_text_snapshot=decision.decision_text,
        confidence_score=1.0,  # 벡터 점수 대신 topic_match가 이미 같은 주제로 확정한 것이라 고정값
        deduplication_key=dedup_key,
        judgment_case=judgment_case,
        **session_kwargs,
        **({"meeting_segment_id": source_id} if source_type == "meeting_segment"
           else {"room_message_id": source_id}),
    )

    if already_popped:
        return {"case": case, "popup": None, "decision_id": str(decision.id)}

    return {
        "case": case,
        "popup": {
            "type": judgment_case,
            "message": message,
            "contradiction_id": str(contradiction.id),
            "actions": ["change_acknowledged", "keep_reference"],
        },
        "decision_id": str(decision.id),
    }
