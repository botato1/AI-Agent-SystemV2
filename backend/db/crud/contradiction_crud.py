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
    1-1 Case 2/3: 세션 내 같은 (decision, judgment_case) 조합에 대해서는 발화가
    여러 개(다른 화자, 다른 값)여도 팝업은 최대 1회만 뜬다. judgment_case를 주지
    않으면 case 구분 없이 decision 단위로만 체크한다.

    [수정] dedup을 decision 단위가 아니라 (decision, case) 단위로 거는 이유: 근거
    명확(reasoned_change)/불명확(unreasoned_change) 여부는 발화마다 바뀔 수 있는
    별개의 알림이라, 한쪽이 이미 떴다고 다른 쪽까지 막으면 안 된다.

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


def resolve_contradiction(
    db: Session,
    contradiction_id: uuid.UUID,
    resolved_by: uuid.UUID,
    resolution_type: str,  # 'change_acknowledged' | 'keep_reference'
    new_decision_text: Optional[str] = None,
    new_decision_reason: Optional[str] = None,
    note: Optional[str] = None,
) -> ContradictionResolution:
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
    """
    resolution = ContradictionResolution(
        contradiction_id=contradiction_id,
        resolved_by=resolved_by,
        resolution_type=resolution_type,
        note=note,
    )
    db.add(resolution)

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
                old_decision.status = "superseded"

                new_decision = Decision(
                    workspace_id=old_decision.workspace_id,
                    meeting_id=old_decision.meeting_id,
                    title=old_decision.title,
                    decision_text=new_decision_text or contradiction.statement_text_snapshot,
                    reason=new_decision_reason,
                    status="active",
                    supersedes_decision_id=old_decision.id,
                    decided_at=contradiction.detected_at,
                )
                db.add(new_decision)

    db.commit()
    db.refresh(resolution)
    return resolution


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
