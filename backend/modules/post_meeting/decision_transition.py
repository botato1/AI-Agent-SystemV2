"""post-meeting 파이프라인 2-3: Decision 상태 전이

LLM 추출 결과(topics[])를 순회하며, 같은 category_id 안 기존 decision과
비교해 분기한다 (설계 문서 2-3 참조).

Case A: 확정 + 값이 다름         → 즉시 반영 안 함. contradictions에 후보로 등록하고
                                   사용자가 /contradictions/{id}/resolve에서
                                   keep_reference(유지)/change_acknowledged(변경,
                                   new_decision_text 지정 시 직접수정)를 선택해야 반영.
Case B: 재논의했지만 결론 없음    → 관련 기존 decision(active/pending) 없으면 새로
                                   status='pending' Decision 생성 (미해결 안건 알림 대상).
                                   있으면 decisions 안 건드리고 기록만.
Case C: 재확인만 함              → 아무것도 안 함
"""

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.crud import contradiction_crud, history_crud
from backend.db.modules import Decision
from backend.modules.llm.ollama_client import OLLAMA_MODEL_HEAVY, _call_ollama
from backend.modules.rag import chroma_client

DECISION_MATCH_THRESHOLD = float(os.getenv("DECISION_MATCH_THRESHOLD", "0.75"))  # TBD - 실험 후 조정 (설계 문서 5장 열린 질문과 동일 축)

COMPARE_PROMPT_TEMPLATE = """아래는 같은 주제에 대한 기존 결정과 새로 논의된 내용이다.
두 값이 실질적으로 같은 내용인지, 다른 내용인지만 판단하라.
다른 설명 없이 "SAME" 또는 "DIFFERENT" 중 하나만 출력하라.

[기존 결정]
{old_text}

[새로 논의된 내용]
{new_text}
"""


def _values_are_same(old_text: str, new_text: str) -> bool:
    """기존 decision과 새 topic의 값이 실질적으로 같은지 LLM으로 판단."""
    prompt = COMPARE_PROMPT_TEMPLATE.format(old_text=old_text, new_text=new_text)
    # [수정 - 2026.07.16] post-meeting은 비동기 처리라 레이턴시 제약 없음 -> 처음부터 Model2
    result = _call_ollama(prompt, timeout=60.0, model=OLLAMA_MODEL_HEAVY).strip().upper()
    return "SAME" in result and "DIFFERENT" not in result


def _find_existing_decision(
    db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, topic_text: str
) -> tuple[Decision, float] | None:
    """DECISION_COLLECTION에서 이 주제와 유사한 기존 decision을 찾는다.
    active/pending 둘 다 대상 - pending 상태에 대해서도 찾아야 같은 미해결 안건이
    회의마다 중복 생성되는 걸 막을 수 있다. 매칭 점수도 함께 반환해서 Case A의
    contradiction confidence_score로 재사용한다 (decision_judgment.py와 동일 패턴)."""
    results = chroma_client.search_hybrid(
        query_text=topic_text,
        workspace_id=str(workspace_id),
        category_id=str(category_id),
        top_k=1,
        collection_name=chroma_client.DECISION_COLLECTION,
    )
    if not results or results[0]["score"] < DECISION_MATCH_THRESHOLD:
        return None

    decision_id = results[0].get("document_id")
    if not decision_id:
        return None

    decision = db.get(Decision, uuid.UUID(decision_id))
    if decision and decision.status in ("active", "pending"):
        return decision, results[0]["score"]
    return None


def process_topics(
    db: Session,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    meeting_id: uuid.UUID,
    topics: list[dict],
    commit: bool = True,
) -> list[Decision]:
    """
    llm_extractor.extract()가 뽑은 topics[]를 순회하며 decisions 테이블을 전이시킨다.

    [수정 - 리뷰 반영 9번] commit 옵션 추가 (post_meeting 파이프라인 단일 트랜잭션용).

    Returns:
        새로 생성되거나 active 상태가 된 decision 목록 (2-5 인덱싱 대상).
        Case A는 즉시 반영되지 않으므로(contradictions에만 등록) 여기 포함되지 않는다.
    """
    newly_active_decisions: list[Decision] = []
    now = datetime.now(timezone.utc)

    for topic in topics:
        status = topic.get("status")
        topic_text = topic.get("decision_text", "") or topic.get("title", "")
        if not topic_text:
            continue

        match = _find_existing_decision(db, workspace_id, category_id, topic_text)
        existing, match_score = match if match else (None, 0.0)

        if status == "reopened_no_conclusion":
            if existing:
                # 이미 관련 decision(active 또는 pending)이 있음 - 중복 생성 방지, 기록만
                history_crud.record_match(
                    db,
                    workspace_id=workspace_id,
                    category_id=category_id,
                    source_type="meeting_segment",
                    match_type="decision_reminder",
                    session_meeting_id=meeting_id,
                    commit=commit,
                    reference_decision_id=existing.id,
                )
            else:
                # 처음 미해결로 논의된 안건 - pending Decision 생성 (agenda_reminder 1-3 조회 대상)
                pending_decision = Decision(
                    workspace_id=workspace_id,
                    meeting_id=meeting_id,
                    title=topic.get("title", "")[:200],
                    decision_text=topic_text,
                    reason=topic.get("reason"),
                    status="pending",
                    decided_at=now,
                )
                db.add(pending_decision)
                newly_active_decisions.append(pending_decision)
            continue

        if not existing:
            # 관련 기존 결정 없음 → 그냥 새 decision 생성 (confirmed/reconfirmed 무관)
            new_decision = Decision(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                title=topic.get("title", "")[:200],
                decision_text=topic_text,
                reason=topic.get("reason"),
                status="active",
                decided_at=now,
            )
            db.add(new_decision)
            newly_active_decisions.append(new_decision)
            continue

        if existing.status != "active":
            # 관련된 게 pending(미해결 안건)뿐이고 아직 active 결정이 아님 - 정식 확정
            # 전이는 스코프 밖(후속 작업), 지금은 그대로 둔다.
            continue

        if status == "reconfirmed":
            # Case C: 재확인만 함, 아무것도 안 함
            continue

        # status == "confirmed": 값이 실제로 다른지 확인
        if _values_are_same(existing.decision_text, topic_text):
            # 사실상 재확인과 동일 (Case C)
            continue

        # Case A: 확정 + 값이 다름 → 즉시 반영하지 않고 모순 후보로 등록.
        # 사용자가 /contradictions/{id}/resolve에서 keep_reference(유지) /
        # change_acknowledged(변경, new_decision_text 지정 시 직접수정)를 선택해야
        # 실제 decisions 테이블에 반영된다 (contradiction_crud.resolve_contradiction 참조).
        dedup_key = contradiction_crud.make_deduplication_key(
            "meeting_summary", meeting_id, existing.id, existing.id
        )
        contradiction_crud.create_contradiction(
            db,
            workspace_id=workspace_id, category_id=category_id,
            source_type="meeting_summary", reference_type="decision",
            reference_decision_id=existing.id,
            statement_text_snapshot=topic_text,
            reference_text_snapshot=existing.decision_text,
            confidence_score=match_score,
            deduplication_key=dedup_key,
            session_meeting_id=meeting_id,
            reason=topic.get("reason"),
            commit=commit,
        )

    if commit:
        db.commit()
        for d in newly_active_decisions:
            db.refresh(d)
    else:
        db.flush()

    return newly_active_decisions
