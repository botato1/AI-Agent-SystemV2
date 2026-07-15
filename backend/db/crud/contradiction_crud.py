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

from backend.db.modules import ChangeSummaryDraft, Contradiction, ContradictionResolution


def make_deduplication_key(
    source_type: str,
    source_id: uuid.UUID,
    reference_file_id: uuid.UUID,
    reference_id: uuid.UUID,
) -> str:
    """같은 조합(발화-기준자료) 재감지 방지용 SHA-256 키."""
    raw = f"{source_type}:{source_id}:{reference_file_id}:{reference_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


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
    reference_file_id: uuid.UUID,
    statement_text_snapshot: str,
    reference_text_snapshot: str,
    confidence_score: float,
    deduplication_key: str,
    severity: str = "medium",
    cooldown_minutes: int = 30,
    **extra_fields,
) -> Contradiction:
    """
    extra_fields로 meeting_segment_id / room_message_id,
    reference_chunk_id / reference_code_fact_id, reason, reference_location 등을 전달.
    (source_type / reference_type과 짝이 맞는 필드만 채워야 DB CHECK 제약 통과)
    """
    row = Contradiction(
        workspace_id=workspace_id,
        category_id=category_id,
        source_type=source_type,
        reference_type=reference_type,
        reference_file_id=reference_file_id,
        statement_text_snapshot=statement_text_snapshot,
        reference_text_snapshot=reference_text_snapshot,
        confidence_score=confidence_score,
        deduplication_key=deduplication_key,
        severity=severity,
        cooldown_until=datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes),
        **extra_fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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


def resolve_contradiction(
    db: Session,
    contradiction_id: uuid.UUID,
    resolved_by: uuid.UUID,
    resolution_type: str,  # 'change_acknowledged' | 'keep_reference'
    note: Optional[str] = None,
) -> ContradictionResolution:
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