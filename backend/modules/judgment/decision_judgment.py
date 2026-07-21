"""실시간 판단 파이프라인 1-1: 결정 비교 판단 (통합)

모순 감지 / 결정 리마인더 / 반복 논의 알림, 이 세 기능은 별개가 아니라 하나의
판단 파이프라인이 결과에 따라 갈라진 것이다 (설계 문서 1-1 참조).

핵심 원칙 — "이미 결정된 걸 다르게 말하는 것 = 모순":
발화가 새로운 값/입장을 제시하는가(→ 값 비교로), 아니면 주제만 재언급하는가
(→ 리마인더)를 먼저 가른다. 재확인이 "글자 그대로 같을 때만"으로 좁아지는 걸
피하기 위함.

2단계 판단:
  1단계) 새 값 제시 여부   → 아니오: Case 0(리마인더)
  2단계) 값이 같은가/사유가 명확한가 → Case 1(무시)/Case 2(조용히 흘림)/
                                         Case 3(모순)/Case 4(보류·반복카운트)
"""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.crud import contradiction_crud, history_crud
from backend.db.modules import Decision
from backend.modules.llm.ollama_client import OLLAMA_MODEL_HEAVY, OLLAMA_MODEL_LIGHT, _call_ollama
from backend.modules.rag import chroma_client

DECISION_MATCH_THRESHOLD = 0.75  # TBD - 실험 후 조정 (post_meeting.decision_transition과 동일 값 사용)
CONTRADICTION_POPUP_THRESHOLD = 0.6  # TBD - confidence 이 값 이상이어야 모순 팝업

JUDGMENT_PROMPT_TEMPLATE = """아래는 회의/채팅에서 방금 나온 발화와, 그것과 관련된 과거 결정이다.
이 둘의 관계를 분석해서 JSON으로만 답하라. 다른 설명은 하지 마라.

[과거 결정]
{decision_text}
(결정 이유: {decision_reason})

[방금 발화]
{statement}

[판단 기준]
1. presents_new_value: 발화가 이 주제에 대해 구체적인 새 값/입장을 제시하는가?
   (단순히 "그거 어떻게 하기로 했죠?" 같은 질문/재언급이면 false)
2. presents_new_value가 true일 때만 아래도 채운다:
   - same_as_existing: 발화의 값이 기존 결정과 실질적으로 같은 내용인가?
   - reason_is_clear: (same_as_existing이 false일 때) 왜 바뀌는지 근거가 발화에 명확히 있는가?
   - confidence: 0.0~1.0, 이 판단에 대한 확신도

[출력 JSON]
{{
  "presents_new_value": true/false,
  "same_as_existing": true/false,
  "reason_is_clear": true/false,
  "confidence": 0.0
}}
"""


def _parse_judgment(raw: str) -> dict:
    fallback = {
        "presents_new_value": False, "same_as_existing": True,
        "reason_is_clear": True, "confidence": 0.0,
    }
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return fallback
        parsed = json.loads(raw[start : end + 1])
        for k, v in fallback.items():
            parsed.setdefault(k, v)
        return parsed
    except (json.JSONDecodeError, ValueError):
        return fallback


def _find_matching_decision(
    workspace_id: uuid.UUID, category_id: uuid.UUID, statement: str
) -> tuple[uuid.UUID, float] | None:
    """
    DECISION_COLLECTION에서 top-1만 채택 (규칙 A - 한 발화=한 주제 가정, MVP 스코프).
    threshold 못 넘으면 None (과거 결정과 무관 → 1-2로 넘어감).
    """
    results = chroma_client.search_hybrid(
        query_text=statement,
        workspace_id=str(workspace_id),
        category_id=str(category_id),
        top_k=1,
        collection_name=chroma_client.DECISION_COLLECTION,
    )
    if not results or results[0]["score"] < DECISION_MATCH_THRESHOLD:
        return None

    document_id = results[0].get("document_id")
    if not document_id:
        return None
    return uuid.UUID(document_id), results[0]["score"]


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
        {"case": "none"|"0"|"1"|"2"|"3"|"4", "popup": dict|None, "decision_id": str|None}
        popup은 팝업을 띄워야 하면 {"type": ..., "message": ...} 형태, 아니면 None.
        "none"은 DECISION_COLLECTION에 애초에 매칭이 없어 1-2로 넘겨야 함을 의미.
    """
    match = _find_matching_decision(workspace_id, category_id, statement)
    if match is None:
        return {"case": "none", "popup": None, "decision_id": None}

    decision_id, match_score = match
    decision = db.get(Decision, decision_id)
    if not decision or decision.status != "active":
        # 매칭은 됐는데 이미 superseded/cancelled인 경우 - 최신 상태가 아니므로 판단 대상 아님
        return {"case": "none", "popup": None, "decision_id": None}

    prompt = JUDGMENT_PROMPT_TEMPLATE.format(
        decision_text=decision.decision_text,
        decision_reason=decision.reason or "명시되지 않음",
        statement=statement,
    )
    # Model1(경량, Qwen2.5-7B)로 1차 판단
    raw = _call_ollama(prompt, timeout=60.0, model=OLLAMA_MODEL_LIGHT)
    judgment = _parse_judgment(raw)

    # [추가 - 2026.07.16] Model1/2 이원화: confidence 낮으면 Model2(Qwen3-8B)로 재판단.
    # presents_new_value=false(Case 0, 리마인더)는 애초에 애매할 여지가 적은 표면
    # 패턴 판단이라 escalate 대상에서 제외 - 새 값 제시가 있다고 판단됐는데
    # (same_as_existing/reason_is_clear까지 포함한) confidence가 낮은 경우만 escalate.
    if judgment["presents_new_value"] and judgment["confidence"] < CONTRADICTION_POPUP_THRESHOLD:
        heavy_raw = _call_ollama(prompt, timeout=150.0, model=OLLAMA_MODEL_HEAVY)
        heavy_judgment = _parse_judgment(heavy_raw)
        # Model2 결과로 교체 (Model2가 더 넓은 컨텍스트/판단력으로 재확인한 결과를 신뢰)
        judgment = heavy_judgment

    session_kwargs = {"session_meeting_id": session_meeting_id, "session_room_id": session_room_id}

    # 1단계: 새 값 제시 여부
    if not judgment["presents_new_value"]:
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
            reference_decision_id=decision.id, confidence_score=match_score,
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
    if judgment["same_as_existing"]:
        # Case 1: 팝업 없음
        return {"case": "1", "popup": None, "decision_id": str(decision.id)}

    if judgment["reason_is_clear"]:
        # Case 2: 정당한 변경 - 실시간 팝업 없이 흘려보냄 (post-meeting Case A로 자연 처리)
        return {"case": "2", "popup": None, "decision_id": str(decision.id)}

    confidence = judgment["confidence"]

    if confidence < CONTRADICTION_POPUP_THRESHOLD:
        # 판단이 애매함 - Case 4 (보류/반복논의)
        history_crud.record_match(
            db,
            workspace_id=workspace_id, category_id=category_id,
            source_type=source_type, match_type="decision_reminder",
            reference_decision_id=decision.id, confidence_score=confidence,
            **session_kwargs,
        )
        repeat_count = history_crud.count_repeat_sessions(db, category_id, decision.id)
        # TODO: 임계치(N) 미정 - 설계 문서 5장 질문 3, 지금은 3회로 임시 설정
        REPEAT_THRESHOLD = 3
        if repeat_count >= REPEAT_THRESHOLD:
            return {
                "case": "4",
                "popup": {
                    "type": "repeat_discussion",
                    "message": f"'{decision.title}'에 대한 논의가 {repeat_count}번째 반복되고"
                               f" 있습니다. 이번 회의에서 확정을 검토해보세요.",
                },
                "decision_id": str(decision.id),
            }
        return {"case": "4", "popup": None, "decision_id": str(decision.id)}

    # Case 3: 모순 - confidence 충분히 높음
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
        confidence_score=confidence,
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