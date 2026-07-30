"""실시간 판단 파이프라인 1-1: 결정 비교 판단 (통합)

모순 감지 / 결정 리마인더 / 반복 논의 알림, 이 세 기능은 별개가 아니라 하나의
판단 파이프라인이 결과에 따라 갈라진 것이다 (설계 문서 1-1 참조).

핵심 원칙 — "이미 결정된 걸 다르게 말하는 것 = 모순":
발화가 새로운 값/입장을 제시하는가(→ 값 비교로), 아니면 주제만 재언급하는가
(→ 리마인더)를 먼저 가른다. 재확인이 "글자 그대로 같을 때만"으로 좁아지는 걸
피하기 위함.

3단계 판단 (전부 Model1 단일 파인튜닝 모델을 배치별 instruction으로 순차 호출):
  1단계) 새 값 제시 여부   → 아니오: Case 0(리마인더)
  2단계) 값이 기존과 같은가 → 예: Case 1(무시)
  3단계) 근거가 명확한가   → 예: Case 2(조용히 흘림) / 아니오: Case 3(모순)

[수정 - 2026.07.27] confidence/Model2 이원화 및 Case 4(보류·반복카운트) 제거.
Case 4는 세션 카운트 기반으로 재설계해서 별도로 다시 넣을 예정 - 지금은 없음.

[수정] 결정 매칭을 벡터 검색(top-1/top-N) 기반에서 topic_match 파인튜닝 검증
기반으로 교체. 벡터 유사도로 후보를 먼저 거르면 임베딩이 약한 진짜 매칭이
후보 밖으로 밀려서 검증 기회 자체가 없어지는 문제가 실측으로 확인됨 - 카테고리당
active decision 개수가 실무적으로 크지 않다는 전제하에, 후보 선별 없이 해당
카테고리의 active decision 전체를 topic_match로 직접 판단한다.
"""

import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.crud import contradiction_crud, history_crud
from backend.db.modules import Decision, Meeting
from backend.modules.llm.ollama_client import _call_ollama

# [수정 - 2026.07.27] confidence/Model2 이원화 제거. 판단은 배치1~4 통합
# 파인튜닝 모델(re-call-model1-unified-v2) 하나로, 단계별 개별 호출.
# ollama_client.OLLAMA_MODEL_LIGHT를 그대로 안 쓰는 이유: 그건 의도분류/일반답변
# 등 다른 기능도 같이 쓰는 공용 상수라, 판단 전용 모델을 거기 넣으면 다른 기능까지
# 좁은 판단용 모델로 넘어가게 됨 - 판단 파이프라인 전용 상수를 따로 둔다.
JUDGMENT_MODEL = os.getenv("OLLAMA_MODEL_JUDGMENT", "re-call-model1-unified-v2")

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

# 배치4(topic_match) 학습 때 쓴 instruction/입력 라벨 그대로 - 문구가 조금이라도
# 다르면 정확도가 크게 떨어짐 (dataset_topic_match_v2.jsonl 참조)
TOPIC_MATCH_INSTRUCTION = (
    "아래는 과거 의사결정과 새 발화이다.\n\n목표:\n새 발화가 과거 의사결정을 수정·대체·조정하려는 내용인지 판단하라.\n\n"
    "같은 주제(true)인 경우\n"
    "- 동일 항목을 다른 기술/서비스/제품으로 교체\n"
    "- 동일 항목의 설정값(수치, 기간, 비율, 개수 등) 변경\n"
    "- 동일 기능을 수행하는 대안 기술 제안\n"
    "- 동일 의사결정의 구현 방식 변경\n\n"
    "다른 주제(false)인 경우\n"
    "- 같은 프로젝트라도 다른 컴포넌트에 대한 이야기\n"
    "- 기존 결정과 독립적인 신규 기능 또는 신규 컴포넌트 제안\n"
    "- 기존 결정과 직접적인 수정 관계가 없는 논의\n\n"
    "판단 기준은 \"같은 기술 분야\"가 아니라\n\"동일한 의사결정을 수정하려는가\"이다."
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
    prompt = (
        f"{TOPIC_MATCH_INSTRUCTION}\n\n{input_text}\n\n"
        f'다음 JSON만 출력한다.\n{{\n  "reason": "20자 이내",\n  "same_topic": true | false\n}}'
    )
    raw = _call_ollama(prompt, timeout=60.0, model=JUDGMENT_MODEL)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return False
        parsed = json.loads(raw[start : end + 1])
        return bool(parsed.get("same_topic", False))
    except (json.JSONDecodeError, ValueError):
        return False


def _get_active_decisions_by_category(
    db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID
) -> list[Decision]:
    """벡터 검색 대신 이 카테고리의 active decision 전체를 Postgres에서 직접 가져온다.
    [수정] 벡터 유사도로 후보를 먼저 거르면 임베딩이 약한 진짜 매칭이 후보에서
    빠질 위험이 있어(실측 확인됨), 후보 선별 자체를 없애고 topic_match가
    전체를 판단하게 한다. Decision엔 category_id가 없어 Meeting을 조인한다."""
    return (
        db.query(Decision)
        .join(Meeting, Decision.meeting_id == Meeting.id)
        .filter(
            Meeting.category_id == category_id,
            Decision.workspace_id == workspace_id,
            Decision.status == "active",
            Decision.deleted_at.is_(None),
        )
        .order_by(Decision.decided_at.desc())
        .all()
    )


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
    candidates = _get_active_decisions_by_category(db, workspace_id, category_id)

    decision = None
    for candidate in candidates:
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

    if reason_is_clear:
        # Case 2: 정당한 변경 - 실시간 팝업 없이 흘려보냄 (post-meeting Case A로 자연 처리)
        return {"case": "2", "popup": None, "decision_id": str(decision.id)}

    # Case 3: 모순 - 근거 불명확 (confidence 제거로 이 분기는 항상 팝업 대상)
    # 규칙 D(임시): 세션 내 같은 decision에 이미 모순 팝업 떴으면 팝업 생략 (기록은 남김)
    already_popped = contradiction_crud.already_popped_in_session_for_decision(
        db, reference_decision_id=decision.id, **session_kwargs
    )

    # make_deduplication_key의 3번째 인자명이 reference_file_id지만, decision 참조도
    # 같은 함수로 dedup key를 만들 수 있어 재사용 (해시 조합용이라 의미상 문제 없음)
    dedup_key = contradiction_crud.make_deduplication_key(
        source_type, source_id, decision.id, decision.id
    )
    contradiction = contradiction_crud.create_contradiction(
        db,
        workspace_id=workspace_id, category_id=category_id,
        source_type=source_type, reference_type="decision",
        reference_decision_id=decision.id,
        statement_text_snapshot=statement,
        reference_text_snapshot=decision.decision_text,
        confidence_score=1.0,  # 벡터 점수 대신 topic_match가 이미 같은 주제로 확정한 것이라 고정값
        deduplication_key=dedup_key,
        **session_kwargs,
        **({"meeting_segment_id": source_id} if source_type == "meeting_segment"
           else {"room_message_id": source_id}),
    )

    if already_popped:
        return {"case": "3", "popup": None, "decision_id": str(decision.id)}

    return {
        "case": "3",
        "popup": {
            "type": "contradiction",
            "message": f"'{statement}'이(가) {decision.decided_at}에 결정된"
                       f" '{decision.decision_text}'와 다릅니다. 바꾸시겠습니까?",
            "contradiction_id": str(contradiction.id),
            "actions": ["change_acknowledged", "keep_reference"],
        },
        "decision_id": str(decision.id),
    }
