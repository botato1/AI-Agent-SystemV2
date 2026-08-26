"""post-meeting 파이프라인 2-3: Decision 상태 전이

LLM 추출 결과(topics[])를 순회하며, 같은 category_id 안 기존 decision과
비교해 분기한다 (설계 문서 2-3 참조).

[수정] "확정 + 값이 다름"(구 Case A) 판단은 여기서 whole-transcript를 다시 읽어
LLM으로 재비교하지 않는다. 실시간 판단 파이프라인(decision_judgment.py Case 2/3)이
이미 발화 단위로 이 판단을 하고 contradictions에 기록해두므로, 회의 후 사용자
확인은 그 기록(세션 내 decision별 최신 행)을 그대로 쓴다 - 중복 판단으로 인한
실시간/사후 판단 불일치를 없애기 위함. 실시간에서 아예 안 잡힌 변경(벡터 후보에서
빠졌거나 발화가 짧아 판단을 못 탄 경우)은 이 경로로도 못 잡는다 - 알려진 한계.

Case B: 재논의했지만 결론 없음    → 관련 기존 decision(active/pending) 없으면 새로
                                   status='pending' Decision 생성 (미해결 안건 알림 대상).
                                   있으면 decisions 안 건드리고 기록만.
그 외(완전히 새로운 decision, 기존 decision과의 재확인/변경)는 아래 process_topics() 참조.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.crud import history_crud
from backend.db.modules import Decision
from backend.modules.judgment import decision_judgment
from backend.modules.rag import chroma_client

# LLM이 topic.status를 스펙대로 못 채우는 경우(누락/오타/대소문자 다름 등) 방어용
# 화이트리스트. 여기 없는 값이면 이 topic 전체를 보수적으로 건너뛴다 - 안 그러면
# 근거 없는 status로 새 decision이 잘못 생성될 수 있다.
_VALID_TOPIC_STATUSES = {"confirmed", "reopened_no_conclusion", "reconfirmed"}


def _find_existing_decision(
    db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, topic_title: str, topic_text: str
) -> Decision | None:
    """DECISION_COLLECTION에서 이 주제와 같은 기존 decision을 찾는다.
    active/pending 둘 다 대상 - pending 상태에 대해서도 찾아야 같은 미해결 안건이
    회의마다 중복 생성되는 걸 막을 수 있다.

    [수정 - 리뷰 반영] 예전엔 벡터 유사도(임계값 0.75) 하나로만 판단했는데,
    pending 안건의 decision_text가 "재논의 중"처럼 뭉뚱그린 문구일 때(핵심
    키워드가 title에만 있고 decision_text엔 없음) 벡터 매칭이 실패해서 같은
    주제인데 별개 decision으로 중복 생성되는 문제가 실사용 테스트에서 확인됨
    (예: "검색 결과 리랭킹 도입 여부"(pending) vs "리랭킹 도입 실행"(새 발화)가
    벡터로는 안 엮이고 둘 다 남음).

    실시간 판단 파이프라인(decision_judgment.py)이 이미 "벡터로 후보 좁히기(느슨한
    임계값) + LLM topic_match로 최종 검증" 2단계 구조로 이 문제를 해결해뒀으므로,
    같은 함수(_ask_topic_match)를 재사용해 여기도 검증 단계를 추가한다. post-meeting은
    비동기 처리라 후보당 LLM 호출이 늘어도 레이턴시 부담이 없다.
    """
    statement = f"{topic_title}: {topic_text}" if topic_title else topic_text

    results = chroma_client.search_hybrid(
        query_text=statement,
        workspace_id=str(workspace_id),
        category_id=str(category_id),
        top_k=decision_judgment.DECISION_CANDIDATE_TOP_K,
        collection_name=chroma_client.DECISION_COLLECTION,
    )
    candidate_ids = [
        r["document_id"] for r in results
        if r.get("document_id") and r["score"] >= decision_judgment.DECISION_CANDIDATE_THRESHOLD
    ]
    if not candidate_ids:
        return None

    for candidate_id in candidate_ids[:decision_judgment.TOPIC_MATCH_MAX_ATTEMPTS]:
        try:
            candidate = db.get(Decision, uuid.UUID(candidate_id))
        except (TypeError, ValueError):
            continue
        if not candidate or candidate.deleted_at is not None or candidate.status not in ("active", "pending"):
            continue
        if decision_judgment._ask_topic_match(
            candidate.decision_text, candidate.reason or "명시되지 않음", statement
        ):
            return candidate

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
    기존 active decision과 매칭되는 경우("값이 바뀌었는지")는 여기서 다루지
    않는다 - 실시간 판단 파이프라인(decision_judgment.py)이 이미 처리한다.
    단, 기존 decision이 pending(미해결) 상태면 confirmed/reconfirmed로 다시
    매칭됐을 때 active로 전이시킨다(아래 [추가] 참조) - "값이 바뀌었는지"가
    아니라 "미해결이 해소됐는지"라 실시간 판단 파이프라인의 스코프 밖이다.

    [수정 - 리뷰 반영 9번] commit 옵션 추가 (post_meeting 파이프라인 단일 트랜잭션용).

    [추가] pending → active 전이 지원. 이전엔 미해결 안건이 나중 회의에서
    명확히 결론나도 계속 미해결로 남는 gap이 있었음.

    Returns:
        새로 생성/pending이 된 decision + 이번에 pending에서 active로
        전이된 decision 목록 (2-5 인덱싱 대상 - 전이된 것도 내용이 바뀌므로
        재인덱싱 필요).
    """
    newly_active_decisions: list[Decision] = []
    now = datetime.now(timezone.utc)

    for topic in topics:
        status = topic.get("status")
        topic_text = topic.get("decision_text", "") or topic.get("title", "")
        if not topic_text:
            continue

        if status not in _VALID_TOPIC_STATUSES:
            print(f"[decision_transition] 알 수 없는 topic status, 보수적으로 스킵: {status!r} (topic={topic_text!r})")
            continue

        existing = _find_existing_decision(db, workspace_id, category_id, topic.get("title", ""), topic_text)

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

        # 기존 active/pending decision과 매칭된 경우 - "값이 바뀌었는지"는 여기서
        # 다시 판단하지 않는다 (위 [수정] 참조, 실시간 판단 파이프라인이 이미 처리).
        #
        # [추가 - 이전엔 스코프 밖(후속 작업)으로 남겨뒀던 부분] pending 상태의
        # 결정이 이번 회의에서 confirmed/reconfirmed로 다시 매칭되면 active로
        # 전이시킨다. 이게 없으면 한 번 미해결(pending)로 남은 안건은 나중에
        # 아무리 명확하게 결론이 나도 미해결 안건 리마인더(agenda_reminder)에
        # 영원히 남는 문제가 있었다. 값/사유/제목도 이번에 확정된 내용으로
        # 갱신하고, 재인덱싱 대상(newly_active_decisions)에 포함시켜 ChromaDB
        # DECISION_COLLECTION에도 최신 내용이 반영되게 한다.
        if existing.status == "pending":
            existing.title = topic.get("title", "")[:200]
            existing.decision_text = topic_text
            existing.reason = topic.get("reason")
            existing.meeting_id = meeting_id
            existing.decided_at = now
            existing.status = "active"
            newly_active_decisions.append(existing)

    if commit:
        db.commit()
        for d in newly_active_decisions:
            db.refresh(d)
    else:
        db.flush()

    return newly_active_decisions
