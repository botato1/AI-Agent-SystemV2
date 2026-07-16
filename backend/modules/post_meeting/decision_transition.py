"""post-meeting 파이프라인 2-3: Decision 상태 전이

LLM 추출 결과(topics[])를 순회하며, 같은 category_id 안 기존 active decision과
비교해 세 가지 케이스로 분기한다 (설계 문서 2-3 참조).

Case A: 확정 + 값이 다름         → 기존 superseded, 새 decision active
Case B: 재논의했지만 결론 없음    → decisions 안 건드림, discussion_points/카운트만
Case C: 재확인만 함              → 아무것도 안 함
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.crud import history_crud
from backend.db.modules import Decision
from backend.modules.llm.ollama_client import _call_ollama
from backend.modules.rag import chroma_client

DECISION_MATCH_THRESHOLD = 0.75  # TBD - 실험 후 조정 (설계 문서 5장 열린 질문과 동일 축)

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
    result = _call_ollama(prompt, timeout=60.0).strip().upper()
    return "SAME" in result and "DIFFERENT" not in result


def _find_existing_active_decision(
    db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, topic_text: str
) -> Decision | None:
    """DECISION_COLLECTION에서 이 주제와 유사한 기존 active decision을 찾는다."""
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
    if decision and decision.status == "active":
        return decision
    return None


def process_topics(
    db: Session,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    meeting_id: uuid.UUID,
    topics: list[dict],
) -> list[Decision]:
    """
    llm_extractor.extract()가 뽑은 topics[]를 순회하며 decisions 테이블을 전이시킨다.

    Returns:
        새로 생성되거나 active 상태가 된 decision 목록 (2-5 인덱싱 대상)
    """
    newly_active_decisions: list[Decision] = []
    now = datetime.now(timezone.utc)

    for topic in topics:
        status = topic.get("status")
        topic_text = topic.get("decision_text", "") or topic.get("title", "")
        if not topic_text:
            continue

        existing = _find_existing_active_decision(db, workspace_id, category_id, topic_text)

        if status == "reopened_no_conclusion":
            # Case B: decisions는 건드리지 않음. 반복 카운트만 기록.
            if existing:
                history_crud.record_match(
                    db,
                    workspace_id=workspace_id,
                    category_id=category_id,
                    source_type="meeting_segment",
                    match_type="decision_reminder",
                    session_meeting_id=meeting_id,
                    reference_decision_id=existing.id,
                )
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

        if status == "reconfirmed":
            # Case C: 재확인만 함, 아무것도 안 함
            continue

        # status == "confirmed": 값이 실제로 다른지 확인
        if _values_are_same(existing.decision_text, topic_text):
            # 사실상 재확인과 동일 (Case C)
            continue

        # Case A: 확정 + 값이 다름 → supersede
        existing.status = "superseded"
        new_decision = Decision(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            title=topic.get("title", "")[:200],
            decision_text=topic_text,
            reason=topic.get("reason"),
            status="active",
            supersedes_decision_id=existing.id,
            decided_at=now,
        )
        db.add(new_decision)
        newly_active_decisions.append(new_decision)

    db.commit()
    for d in newly_active_decisions:
        db.refresh(d)

    return newly_active_decisions