"""모순 감지 CRUD — 내 파트

파이프라인: meeting_segment/room_message 생성
  -> 벡터화 -> ChromaDB 검색 -> code_facts 값 비교 -> LLM 판단
  -> confidence 임계값 검사 -> dedup 체크 -> contradictions 저장 -> 알림
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from backend.db.modules import ChangeSummaryDraft, Contradiction, ContradictionResolution, MeetingSegment
from backend.modules.llm.ollama_client import _call_ollama, OLLAMA_MODEL_LIGHT


def make_deduplication_key(
    source_type: str,
    source_id: uuid.UUID,
    reference_file_id: uuid.UUID,
    reference_id: uuid.UUID,
) -> str:
    """같은 조합(발화-기준자료) 재감지 방지용 SHA-256 키."""
    raw = f"{source_type}:{source_id}:{reference_file_id}:{reference_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def already_popped_in_session_for_decision(
    db: Session,
    *,
    session_meeting_id: Optional[uuid.UUID] = None,
    session_room_id: Optional[uuid.UUID] = None,
    reference_decision_id: uuid.UUID,
    judgment_case: Optional[str] = None,
) -> bool:
    """
    1-1 Case 2/3: 세션 내 같은 (decision, judgment_case) 조합이 이미 있었는지 체크하는
    저수준 함수. judgment_case를 주지 않으면 case 구분 없이 decision 단위로만 체크한다.

    [수정 - 라이브 테스트 발견] 이 함수 자체는 항상 정확히 지정된 (decision, case)
    조합만 체크하지만, 실제 팝업 노출 정책(호출부인 decision_judgment.py)은 더 이상
    "case가 다르면 무조건 각각 1회씩" 대칭 dedup이 아니다 - Case 2(근거 명확)가 세션 내
    한 번이라도 떴으면 그 이후 Case 3(근거 불명확)은 정보 퇴보라 무시하고, 반대로
    Case 3이 먼저 떴어도 Case 2는 새 정보라 띄우는 비대칭 규칙으로 바뀌었다 (같은 발화가
    STT 분절로 쪼개져 "근거 없이 바뀜"→"근거 대며 바뀜"이 모순되게 동시에 뜨던 버그 수정).
    자세한 정책은 decision_judgment.py의 호출부 주석 참조.

    이 함수는 팝업 노출 여부만 결정하고, contradictions row 자체는 dedup 여부와
    무관하게 항상 생성된다 (감사기록 + post-meeting이 세션 내 최신 행을 그대로
    사용자 확인 대상으로 재사용하는 근거가 됨 - decision_transition.py 참조).
    """
    q = db.query(Contradiction).filter(
        Contradiction.reference_decision_id == reference_decision_id,
        Contradiction.reference_type == "decision",
    )
    if judgment_case:
        q = q.filter(Contradiction.judgment_case == judgment_case)
    if session_meeting_id:
        q = q.filter(Contradiction.session_meeting_id == session_meeting_id)
    if session_room_id:
        q = q.filter(Contradiction.session_room_id == session_room_id)
    return db.query(q.exists()).scalar()


def is_in_cooldown(db: Session, workspace_id: uuid.UUID, dedup_key: str) -> bool:
    """같은 문서 청크 기준 쿨다운 체크."""
    row = (
        db.query(Contradiction)
        .filter(
            Contradiction.workspace_id == workspace_id,
            Contradiction.deduplication_key == dedup_key,
            Contradiction.cooldown_until.isnot(None),
        )
        .order_by(Contradiction.detected_at.desc())
        .first()
    )
    if not row or not row.cooldown_until:
        return False
    # [수정 사항 - 2026.07.15] 리뷰 피드백 반영: naive/aware datetime 혼용 버그
    # cooldown_until 컬럼은 DateTime(timezone=True)라 DB에서 항상 tz-aware로
    # 돌아온다. 기존엔 naive(datetime.utcnow())를 만들어서 row 쪽을 억지로
    # naive로 깎아 비교했는데, 세션 타임존이 UTC가 아니면 조용히 틀어질 수
    # 있었음. 양쪽 다 tz-aware(UTC)로 통일해서 비교.
    return datetime.now(timezone.utc) < row.cooldown_until


def create_contradiction(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    source_type: str,
    reference_type: str,
    statement_text_snapshot: str,
    reference_text_snapshot: str,
    confidence_score: float,
    deduplication_key: str,
    reference_file_id: Optional[uuid.UUID] = None,
    reference_decision_id: Optional[uuid.UUID] = None,
    session_meeting_id: Optional[uuid.UUID] = None,
    session_room_id: Optional[uuid.UUID] = None,
    severity: str = "medium",
    cooldown_minutes: int = 30,
    commit: bool = True,
    **extra_fields,
) -> Contradiction:
    """
    extra_fields로 meeting_segment_id / room_message_id,
    reference_chunk_id / reference_code_fact_id, reason, reference_location 등을 전달.
    (source_type / reference_type과 짝이 맞는 필드만 채워야 DB CHECK 제약 통과)

    reference_type='decision'인 경우 reference_file_id 대신 reference_decision_id를,
    session_meeting_id 또는 session_room_id를 반드시 채워야
    already_popped_in_session_for_decision()으로 세션당 1회 체크가 가능하다.

    [추가] commit=False면 flush만 하고 커밋은 호출부에 맡긴다 - post_meeting
    파이프라인의 원자적 1단계 커밋 구조에 이 함수가 끼어들 때 필요.
    """
    row = Contradiction(
        workspace_id=workspace_id,
        category_id=category_id,
        source_type=source_type,
        reference_type=reference_type,
        reference_file_id=reference_file_id,
        reference_decision_id=reference_decision_id,
        session_meeting_id=session_meeting_id,
        session_room_id=session_room_id,
        statement_text_snapshot=statement_text_snapshot,
        reference_text_snapshot=reference_text_snapshot,
        confidence_score=confidence_score,
        deduplication_key=deduplication_key,
        severity=severity,
        cooldown_until=datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes),
        **extra_fields,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row

def delete_contradictions_by_reference_file(db: Session, file_id: uuid.UUID) -> int:
    """해당 파일의 청크를 참조하는 contradictions를 하위 레코드(변경요약 초안,
    해결 이력)까지 포함해 전부 삭제한다. 문서 삭제 시 FK 위반
    (contradictions_reference_chunk_id_fkey)을 막기 위해 청크 삭제 전에 호출해야 한다."""
    contradiction_ids = [
        c.id for c in
        db.query(Contradiction).filter(Contradiction.reference_file_id == file_id).all()
    ]
    if not contradiction_ids:
        return 0

    db.query(ChangeSummaryDraft).filter(
        ChangeSummaryDraft.contradiction_id.in_(contradiction_ids)
    ).delete(synchronize_session=False)
    db.query(ContradictionResolution).filter(
        ContradictionResolution.contradiction_id.in_(contradiction_ids)
    ).delete(synchronize_session=False)
    db.query(Contradiction).filter(
        Contradiction.id.in_(contradiction_ids)
    ).delete(synchronize_session=False)
    db.commit()
    return len(contradiction_ids)


def list_unresolved(db: Session, workspace_id: uuid.UUID) -> list[Contradiction]:
    return (
        db.query(Contradiction)
        .filter(
            Contradiction.workspace_id == workspace_id,
            Contradiction.status == "unresolved",
        )
        .order_by(Contradiction.detected_at.desc())
        .all()
    )


def list_unresolved_by_category(db: Session, category_id: uuid.UUID) -> list[Contradiction]:
    """대시보드(카테고리 단위) 모순 감지 로그용."""
    return (
        db.query(Contradiction)
        .filter(
            Contradiction.category_id == category_id,
            Contradiction.status == "unresolved",
        )
        .order_by(Contradiction.detected_at.desc())
        .all()
    )

def get_contradiction(db: Session, contradiction_id: uuid.UUID) -> Optional[Contradiction]:
    return db.query(Contradiction).filter(Contradiction.id == contradiction_id).first()


def list_contradictions(
    db: Session, workspace_id: uuid.UUID, status: Optional[str] = None
) -> list[Contradiction]:
    query = db.query(Contradiction).filter(Contradiction.workspace_id == workspace_id)
    if status:
        query = query.filter(Contradiction.status == status)
    return query.order_by(Contradiction.detected_at.desc()).all()


def dismiss_contradiction(db: Session, contradiction_id: uuid.UUID) -> Optional[Contradiction]:
    row = db.get(Contradiction, contradiction_id)
    if row:
        row.status = "dismissed"
        db.commit()
        db.refresh(row)
    return row

def get_resolution(db: Session, contradiction_id: uuid.UUID) -> Optional[ContradictionResolution]:
    return (
        db.query(ContradictionResolution)
        .filter(ContradictionResolution.contradiction_id == contradiction_id)
        .first()
    )


def reopen_contradiction(db: Session, contradiction_id: uuid.UUID) -> Optional[Contradiction]:
    """keep_reference로 해결됐던 모순을 다시 unresolved로 되돌린다.
    change_acknowledged는 decisions 테이블 전이까지 일으키므로 되돌리기 대상에서
    제외해야 한다 - 그 검증은 호출부(라우터)에서 미리 하고, 여기선 단순히
    해결 기록을 지우고 상태만 되돌린다."""
    contradiction = db.get(Contradiction, contradiction_id)
    if not contradiction:
        return None

    resolution = get_resolution(db, contradiction_id)
    if resolution:
        db.delete(resolution)

    contradiction.status = "unresolved"
    db.commit()
    db.refresh(contradiction)
    return contradiction


def get_change_summary_draft(db: Session, contradiction_id: uuid.UUID) -> Optional[ChangeSummaryDraft]:
    return (
        db.query(ChangeSummaryDraft)
        .filter(ChangeSummaryDraft.contradiction_id == contradiction_id)
        .first()
    )


def _revise_short_summary(original_short_summary: str, old_text: str, new_text: str) -> Optional[str]:
    """[추가 - 2026.08.18] "직접수정해서 반영" 시 회의 요약 카드의 한 줄 요약에서
    이번에 바뀐 결정 관련 부분만 새 내용으로 고쳐 쓴다.

    전체를 다시 요약하게 하면 상관없는 문장까지 손댈 위험이 있어서, 프롬프트로
    "그 부분만 고치고 나머지는 그대로 유지"를 강하게 제약한다. 그래도 LLM이라
    통째로 다시 쓰거나 형식이 깨질 수 있어 길이 기반 안전장치를 둔다 - 원문
    대비 절반 미만/2배 초과로 달라지면 신뢰하지 않고 None을 반환해 호출부가
    원본을 그대로 둔다 (실패해도 위의 decision 전이 자체는 이미 커밋된 뒤라
    핵심 기능에는 영향 없음)."""
    prompt = (
        "아래는 회의의 한 줄 요약 문장이다.\n\n"
        f"[기존 한 줄 요약]\n{original_short_summary}\n\n"
        f"[옛 결정 내용]\n{old_text}\n\n"
        f"[새로 확정된 내용]\n{new_text}\n\n"
        "위 한 줄 요약에서 [옛 결정 내용]과 관련된 부분만 [새로 확정된 내용]을 "
        "반영해서 자연스럽게 고쳐라. 관련 없는 나머지 문장·표현은 절대 바꾸지 말고 "
        "원문 그대로 유지하라. 개조식(~함/~임 등 명사형 종결) 문체를 유지하라. "
        "다른 설명 없이 고쳐진 한 줄 요약 문장만 출력하라."
    )
    # [수정 - 리뷰 반영] 독자적으로 OLLAMA_MODEL/httpx를 재선언해서 호출하던 것을
    # 공용 _call_ollama()로 통일 - contradiction_detect.py/ai_chat_answer.py와
    # 동일한 이유(운영자가 OLLAMA_MODEL_LIGHT/HEAVY만 설정하고 레거시
    # OLLAMA_MODEL은 안 건드리면 이 함수만 다른 모델을 쓰게 됨) + 중국어 출력
    # 재시도 로직도 이걸 통해야 같이 받을 수 있음. keep_alive도 이 함수 안에
    # 이미 포함돼 있어 모델 재로드 지연 문제도 별도 조치 없이 해결됨.
    try:
        revised = _call_ollama(prompt, model=OLLAMA_MODEL_LIGHT, temperature=0).strip()
    except Exception as e:
        print(f"[resolve_contradiction] 한 줄 요약 갱신 LLM 호출 실패: {repr(e)}")
        return None

    if not revised:
        return None

    orig_len = len(original_short_summary)
    if len(revised) < orig_len * 0.5 or len(revised) > orig_len * 2:
        print(
            f"[resolve_contradiction] 한 줄 요약 갱신 결과가 원문과 길이 차이가 커서 무시함 "
            f"(원본 {orig_len}자 -> 결과 {len(revised)}자)"
        )
        return None
    return revised


def _rewrite_as_formal_decision_text(statement: str) -> Optional[str]:
    """[추가 - 리뷰 반영] "직접수정해서 반영" 시 만들어지는 새 decision의 decision_text가
    발화 원문(구어체) 그대로 저장되던 문제 수정. post-meeting이 만드는 다른 decision들은
    llm_extractor.py의 지침대로 개조식(~함/~임)으로 다듬어지는데, 이 경로만 다듬는 단계가
    없어서 같은 화면 안에서 문구 톤이 서로 안 맞았음(라이브 테스트에서 발견).

    실패 시 None을 반환해 호출부가 원문(statement)을 그대로 쓰게 한다(폴백)."""
    prompt = (
        "아래 발화를 회의록에 쓰는 결정사항 문구로 간결하게 다듬어라. "
        "개조식(\"~함\", \"~임\", \"~됨\" 등으로 끝나는 명사형 종결)으로 쓰고, "
        "\"~습니다\", \"~해요\" 같은 평서문/구어체는 쓰지 않는다. "
        "원래 의미를 바꾸지 말고, 다른 설명 없이 다듬어진 문구만 출력하라.\n\n"
        f"[발화]\n{statement}"
    )
    try:
        rewritten = _call_ollama(prompt, model=OLLAMA_MODEL_LIGHT, temperature=0).strip()
    except Exception as e:
        print(f"[resolve_contradiction] decision_text 개조식 변환 실패(원문으로 폴백): {repr(e)}")
        return None
    return rewritten or None


def resolve_contradiction(
    db: Session,
    contradiction_id: uuid.UUID,
    resolved_by: uuid.UUID,
    resolution_type: str,  # 'change_acknowledged' | 'keep_reference'
    new_decision_text: Optional[str] = None,
    new_decision_reason: Optional[str] = None,
    note: Optional[str] = None,
) -> tuple[ContradictionResolution, Optional[str]]:
    """
    [수정 - 2026.07.16] decision 대비 모순("변경 인지함") 처리 시 실제로
    decisions 테이블을 전이시키는 로직 추가.

    기존엔 contradiction.status만 resolved로 바뀌고 change_summary_drafts만
    생성됐지, contradiction.reference_type='decision'인 경우에도 decisions
    테이블 자체는 전혀 안 바뀌었음. 그러면 같은 회의 안에서 다음 발화가
    또 같은(옛) decision과 비교될 때 여전히 모순으로 다시 잡히는 문제가 있었음.

    change_acknowledged + reference_type='decision'이면 post-meeting의
    Case A(재결정)와 동일한 전이를 실시간으로 수행한다:
      기존 decision.status = 'superseded'
      새 decision 생성, status = 'active', supersedes_decision_id = 기존.id

    [수정 - 리뷰 반영] 반환값을 (resolution, resolved_decision_text) 튜플로 변경.
    new decision을 만들 때 실제로 저장한 decision_text(개조식으로 다듬어진 값, 또는
    다듬기 실패 시 원문)를 호출부(라우터)가 알 수 있는 방법이 없어서,
    create_change_summary_draft()에는 여전히 구어체 원문(statement_text_snapshot)이
    들어가 결정사항 이력과 변경 요약 카드의 문구 톤이 서로 어긋나는 문제가 있었음.
    new decision을 안 만든 경우(keep_reference 등)엔 두 번째 값이 None.
    """
    resolution = ContradictionResolution(
        contradiction_id=contradiction_id,
        resolved_by=resolved_by,
        resolution_type=resolution_type,
        note=note,
    )
    db.add(resolution)

    resolved_decision_text: Optional[str] = None

    contradiction = db.get(Contradiction, contradiction_id)
    if contradiction:
        contradiction.status = "resolved"

        if (
            resolution_type == "change_acknowledged"
            and contradiction.reference_type == "decision"
            and contradiction.reference_decision_id is not None
        ):
            from backend.db.modules import Decision

            old_decision = db.get(Decision, contradiction.reference_decision_id)
            if old_decision and old_decision.status == "active":
                # [수정 - 리뷰 반영] old_decision.status 변경(UPDATE) 전에 먼저
                # decision_text를 확정한다. _rewrite_as_formal_decision_text()가
                # 느린 LLM 호출인데, UPDATE를 먼저 걸어놓고 그 아래서 LLM을
                # 기다리면 커밋 전까지 그 UPDATE의 행 잠금이 계속 열려있게 됨 -
                # 여기서는 아직 SELECT만 실행된 상태라 잠금 위험 없이 대기 가능.
                decision_text = new_decision_text or _rewrite_as_formal_decision_text(
                    contradiction.statement_text_snapshot
                ) or contradiction.statement_text_snapshot
                resolved_decision_text = decision_text

                old_decision.status = "superseded"

                # [수정 - 라이브 테스트 발견] meeting_id를 old_decision.meeting_id(그
                # 결정이 원래 확정됐던 옛날 회의)로 넣고 있었음 - 지금 이 변경을 실제로
                # 확인/확정한 건 현재 회의인데, 새 decision이 옛날 회의 소속으로 생겨서
                # list_decisions_by_meeting(현재_회의_id) 조회 시 안 잡혀 "직접수정해서
                # 반영"해도 회의 요약/회의록에는 안 보이는 문제로 이어짐.
                # contradiction.session_meeting_id가 바로 그 "현재 회의"임 -
                # _check_not_chat_sourced()가 채팅발 모순은 resolve 자체를 막아서
                # source_type이 항상 meeting_segment일 때만 여기 도달하므로 항상 채워져
                # 있음(방어적으로 old_decision.meeting_id를 fallback으로 남김).
                new_decision = Decision(
                    workspace_id=old_decision.workspace_id,
                    meeting_id=contradiction.session_meeting_id or old_decision.meeting_id,
                    title=old_decision.title,
                    decision_text=decision_text,
                    reason=new_decision_reason,
                    status="active",
                    supersedes_decision_id=old_decision.id,
                    decided_at=contradiction.detected_at,
                )
                db.add(new_decision)

    db.commit()
    db.refresh(resolution)
    return resolution, resolved_decision_text


def regenerate_short_summary_after_change(contradiction_id: uuid.UUID) -> None:
    """[수정 - 리뷰 반영] "직접수정해서 반영" 시 요약 카드의 한 줄 요약을 갱신하는
    LLM 호출을 resolve_contradiction() 안에서 동기로 하던 것을 떼어냈다.
    change_summary_generate_node와 같은 이유(_ask_topic_match 등과 달리 이건
    사용자 응답을 막을 이유가 없는 부가 처리) - 라우터가 change_acknowledged
    처리 직후 background_tasks.add_task(...)로 이 함수를 스케줄해야 한다.

    요청 스코프 db 세션을 백그라운드 태스크에 그대로 넘기면 응답이 나간 뒤
    세션이 이미 닫혀있을 수 있어 위험하다 - change_summary_generate_node와
    동일하게 이 함수가 독립적으로 자기 세션을 열고 닫는다. resolve_contradiction()
    이 이미 커밋해놓은 old_decision(superseded)/new_decision(active,
    supersedes_decision_id로 연결)을 contradiction_id로부터 다시 조회한다.
    """
    from backend.db.session import SessionLocal
    from backend.db.crud import meeting_crud
    from backend.db.modules import Decision

    db = SessionLocal()
    try:
        contradiction = db.get(Contradiction, contradiction_id)
        if not contradiction or contradiction.reference_decision_id is None:
            return

        old_decision = db.get(Decision, contradiction.reference_decision_id)
        if not old_decision:
            return

        new_decision = (
            db.query(Decision)
            .filter(Decision.supersedes_decision_id == old_decision.id)
            .order_by(Decision.created_at.desc())
            .first()
        )
        if not new_decision:
            return

        summary_row = meeting_crud.get_meeting_summary(db, new_decision.meeting_id)
        if not summary_row or not summary_row.short_summary:
            return

        revised = _revise_short_summary(
            summary_row.short_summary, old_decision.decision_text, new_decision.decision_text,
        )
        if revised:
            meeting_crud.upsert_summary(db, new_decision.meeting_id, short_summary=revised)
    except Exception as e:
        print(f"[regenerate_short_summary_after_change] 처리 중 예외 발생(무시): {repr(e)}")
    finally:
        db.close()


def create_change_summary_draft(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    resolution_id: uuid.UUID,
    context_type: str,  # 'meeting' | 'chat'
    original_reference_text: str,
    accepted_change_text: str,
    **extra_fields,
) -> ChangeSummaryDraft:
    """change_acknowledged 처리 시에만 호출. LLM 요약 생성은 상위 서비스에서."""
    row = ChangeSummaryDraft(
        workspace_id=workspace_id,
        contradiction_id=contradiction_id,
        resolution_id=resolution_id,
        context_type=context_type,
        original_reference_text=original_reference_text,
        accepted_change_text=accepted_change_text,
        generation_status="pending",
        **extra_fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_change_summary_draft(
    db: Session, contradiction_id: uuid.UUID, **fields
) -> Optional[ChangeSummaryDraft]:
    """generation_status/generated_summary/generation_error/model_name 등을 부분 갱신한다."""
    row = get_change_summary_draft(db, contradiction_id)
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
    return row

def count_by_meeting(db: Session, meeting_id: uuid.UUID) -> int:
    """session_meeting_id(결정 기반)와 meeting_segment_id 역추적(문서 기반) 둘 다 커버한다."""
    return (
        db.query(Contradiction)
        .outerjoin(MeetingSegment, Contradiction.meeting_segment_id == MeetingSegment.id)
        .filter(
            or_(
                Contradiction.session_meeting_id == meeting_id,
                MeetingSegment.meeting_id == meeting_id,
            )
        )
        .count()
    )

def count_in_range(db: Session, workspace_id: uuid.UUID, start: datetime, end: datetime) -> int:
    return (
        db.query(Contradiction)
        .filter(
            Contradiction.workspace_id == workspace_id,
            Contradiction.detected_at >= start,
            Contradiction.detected_at < end,
        )
        .count()
    )

def list_latest_decision_changes_by_meeting(db: Session, meeting_id: uuid.UUID) -> list[Contradiction]:
    """회의 종료 후 사용자에게 보여줄 decision 변경 후보 목록.

    같은 reference_decision_id에 대해 회의 중 여러 번 값이 바뀌었으면
    가장 최근(detected_at) 것 하나만 노출한다 (승주 확인).
    """
    latest_per_decision = (
        db.query(
            Contradiction.reference_decision_id,
            func.max(Contradiction.detected_at).label("latest_detected_at"),
        )
        .filter(
            Contradiction.session_meeting_id == meeting_id,
            Contradiction.reference_type == "decision",
            Contradiction.status == "unresolved",
        )
        .group_by(Contradiction.reference_decision_id)
        .subquery()
    )

    return (
        db.query(Contradiction)
        .join(
            latest_per_decision,
            (Contradiction.reference_decision_id == latest_per_decision.c.reference_decision_id)
            & (Contradiction.detected_at == latest_per_decision.c.latest_detected_at),
        )
        .filter(
            Contradiction.session_meeting_id == meeting_id,
            Contradiction.reference_type == "decision",
            Contradiction.status == "unresolved",
        )
        .all()
    )

def update_contradiction_snapshots(
    db: Session, contradiction_id: uuid.UUID,
    statement_text_snapshot: Optional[str] = None,
    reference_text_snapshot: Optional[str] = None,
) -> Optional[Contradiction]:
    contradiction = db.get(Contradiction, contradiction_id)
    if not contradiction:
        return None
    if statement_text_snapshot is not None:
        contradiction.statement_text_snapshot = statement_text_snapshot
    if reference_text_snapshot is not None:
        contradiction.reference_text_snapshot = reference_text_snapshot
    db.commit()
    db.refresh(contradiction)
    return contradiction
