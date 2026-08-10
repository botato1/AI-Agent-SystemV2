# backend/routers/contradiction_router.py

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import contradiction_crud, file_crud, meeting_crud, notification_crud, workspace_crud
from backend.db.modules import Decision

from backend.graphs.change_summary_graph import run_change_summary_generation
from backend.schemas.contradiction_schema import (
    ContradictionSchema,
    ContradictionListResponse,
    ContradictionResolveRequest,
    ChangeSummaryDraftSchema,
    ContradictionUpdateRequest,
)
from backend.schemas.type_schema import ContradictionStatus


router = APIRouter(prefix="/api/workspaces/{workspace_id}/contradictions", tags=["Contradictions"])


def _get_contradiction_or_404(db: Session, contradiction_id: uuid.UUID, workspace_id: uuid.UUID):
    contradiction = contradiction_crud.get_contradiction(db, contradiction_id)
    if not contradiction or contradiction.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="모순 항목을 찾을 수 없습니다.",
        )
    return contradiction

def _resolve_source_meeting(db: Session, contradiction):
    """session_meeting_id(결정 기반) 우선, 없으면 meeting_segment_id로 역추적(문서 기반)."""
    if contradiction.session_meeting_id:
        return meeting_crud.get_meeting(db, contradiction.session_meeting_id)
    if contradiction.meeting_segment_id:
        segment = meeting_crud.get_segment(db, contradiction.meeting_segment_id)
        if segment:
            return meeting_crud.get_meeting(db, segment.meeting_id)
    return None

def _check_meeting_not_recording(db: Session, contradiction) -> None:
    """회의가 아직 진행 중(recording)이면 모순 처리(해결/무시)를 거부한다.
    회의 종료 후 한 번에 일괄 정리하도록 유도하기 위함 (교수님 피드백 반영)."""
    meeting = _resolve_source_meeting(db, contradiction)
    if meeting and meeting.status == "recording":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="회의가 진행 중일 때는 모순을 처리할 수 없습니다. 회의 종료 후 처리해주세요.",
        )
    
def _check_not_chat_sourced(contradiction, resolution_type: str | None = None) -> None:
    """채팅발 모순 중, decision 변경을 실제로 확정(전이)하는 조합만 막는다.
    change_acknowledged + reference_type='decision'이면 decisions 테이블 전이가
    일어나는데 RAG(decision_collection) 재인덱싱이 안 됨 - dismiss/keep_reference/
    문서(content_chunk) 참조는 이 경로를 안 타므로 막을 이유 없음."""
    if (
        contradiction.source_type == "room_message"
        and contradiction.reference_type == "decision"
        and resolution_type == "change_acknowledged"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="채팅에서 감지된 결정 변경은 아직 반영할 수 없습니다. 회의에서 다시 확인해주세요.",
        )


def _resolve_reference_meeting(db: Session, contradiction):
    """reference_type이 decision일 때만 — 그 결정이 나온 회의."""
    if contradiction.reference_type == "decision" and contradiction.reference_decision_id:
        decision = db.get(Decision, contradiction.reference_decision_id)
        if decision:
            return meeting_crud.get_meeting(db, decision.meeting_id)
    return None

def _to_contradiction_schema(db: Session, contradiction) -> ContradictionSchema:
    """reference_type에 따라 근거 자료의 이름(파일명/결정 제목)을 채워서 반환한다.
    프론트가 '기준: system_spec.pdf' 처럼 사람이 알아볼 수 있게 표시할 수 있게 함."""
    source_name = None
    if contradiction.reference_type == "content_chunk" and contradiction.reference_file_id:
        file = file_crud.get_file(db, contradiction.reference_file_id)
        source_name = file.original_filename if file else None
    elif contradiction.reference_type == "decision" and contradiction.reference_decision_id:
        decision = db.get(Decision, contradiction.reference_decision_id)
        source_name = decision.title if decision else None

    excerpt = " ".join((contradiction.reference_text_snapshot or "").split())[:100]

    if contradiction.reference_type == "decision" and contradiction.judgment_case:
        reason_text = contradiction.reason or "사유 미기재"
        if contradiction.judgment_case == "reasoned_change":
            display_message = (
                f"근거가 확인되어 결정이 바뀐 것으로 보입니다: '{contradiction.statement_text_snapshot}'"
                f" (기존: '{contradiction.reference_text_snapshot}', 사유: {reason_text})."
            )
        else:  # unreasoned_change
            display_message = (
                f"명확한 근거 없이 결정이 바뀐 것으로 보입니다: '{contradiction.statement_text_snapshot}'"
                f" (기존: '{contradiction.reference_text_snapshot}', 사유: {reason_text})."
            )
    elif source_name and excerpt:
        display_message = (
            f"'{contradiction.statement_text_snapshot}'라고 하셨는데, "
            f"기존 자료({source_name})의 '{excerpt}'와 다릅니다."
        )
    elif excerpt:
        display_message = (
            f"'{contradiction.statement_text_snapshot}'라고 하셨는데, "
            f"기존 자료의 '{excerpt}'와 다릅니다."
        )
    else:
        display_message = (
            f"'{contradiction.statement_text_snapshot}'라고 하셨는데, 기존 자료와 다릅니다."
        )

    resolution = contradiction_crud.get_resolution(db, contradiction.id)

    schema = ContradictionSchema.model_validate(contradiction)
    schema.reference_source_name = source_name
    schema.display_message = display_message
    schema.resolution_type = resolution.resolution_type if resolution else None

    source_meeting = _resolve_source_meeting(db, contradiction)
    if source_meeting:
        schema.source_meeting_title = source_meeting.title
        schema.source_meeting_time = source_meeting.started_at
        if contradiction.source_type == "meeting_segment":
            schema.meeting_id = source_meeting.id

    reference_meeting = _resolve_reference_meeting(db, contradiction)
    if reference_meeting:
        schema.reference_meeting_title = reference_meeting.title
        schema.reference_meeting_time = reference_meeting.started_at

    return schema


def _notify_contradiction_resolved(db: Session, workspace_id: uuid.UUID, contradiction) -> None:
    for member, _user in workspace_crud.list_members(db, workspace_id):
        if not notification_crud.is_notification_enabled(
            db, workspace_id, member.user_id, "contradiction_resolved",
        ):
            continue
        notification_crud.create_notification(
            db, user_id=member.user_id, workspace_id=workspace_id,
            type="contradiction_resolved", title="모순 해결됨",
            message=f"'{contradiction.statement_text_snapshot}' 관련 모순이 처리되었습니다.",
            ref_type="contradiction", ref_id=contradiction.id,
        )


# 모순 목록 조회
@router.get("", response_model=ContradictionListResponse)
def get_contradiction_list(
    workspace_id: uuid.UUID,
    status_filter: Optional[ContradictionStatus] = Query(default=None, alias="status"),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    items = contradiction_crud.list_contradictions(db, workspace_id, status=status_filter)
    return ContradictionListResponse(
        contradictions=[_to_contradiction_schema(db, c) for c in items]
    )

# 회의 종료 후 decision 변경 후보 조회 (같은 decision당 최신 1건만)
@router.get("/meetings/{meeting_id}/decision-changes", response_model=ContradictionListResponse)
def get_meeting_decision_changes_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    items = contradiction_crud.list_latest_decision_changes_by_meeting(db, meeting_id)
    return ContradictionListResponse(
        contradictions=[_to_contradiction_schema(db, c) for c in items]
    )


# 모순 단건 조회
@router.get("/{contradiction_id}", response_model=ContradictionSchema)
def get_contradiction_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    contradiction = _get_contradiction_or_404(db, contradiction_id, workspace_id)
    return _to_contradiction_schema(db, contradiction)


# 모순 해결
@router.post("/{contradiction_id}/resolve", response_model=ContradictionSchema)
def resolve_contradiction_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    request: ContradictionResolveRequest,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    contradiction = _get_contradiction_or_404(db, contradiction_id, workspace_id)

    if contradiction.status != "unresolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 모순입니다.",
        )
    _check_meeting_not_recording(db, contradiction)
    _check_not_chat_sourced(contradiction, request.resolution_type)
    
    resolution = contradiction_crud.resolve_contradiction(
        db,
        contradiction_id=contradiction_id,
        resolved_by=uuid.UUID(current_user_id),
        resolution_type=request.resolution_type,
        note=request.note,
    )

    _notify_contradiction_resolved(db, workspace_id, contradiction)

    if request.resolution_type == "change_acknowledged":
        context_type = "meeting" if contradiction.source_type == "meeting_segment" else "chat"
        contradiction_crud.create_change_summary_draft(
            db,
            workspace_id=workspace_id,
            contradiction_id=contradiction_id,
            resolution_id=resolution.id,
            context_type=context_type,
            original_reference_text=contradiction.reference_text_snapshot,
            accepted_change_text=contradiction.statement_text_snapshot,
        )
        # 요약 생성은 백그라운드로 — 응답은 draft가 pending인 채로 바로 나가고,
        # 프론트는 GET .../change-summary로 완료 여부를 폴링한다.
        background_tasks.add_task(
            run_change_summary_generation,
            contradiction_id=str(contradiction_id),
            workspace_id=str(workspace_id),
            category_id=str(contradiction.category_id),
        )

    updated = contradiction_crud.get_contradiction(db, contradiction_id)
    return _to_contradiction_schema(db, updated)


# 모순 무시
@router.post("/{contradiction_id}/dismiss", response_model=ContradictionSchema)
def dismiss_contradiction_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    contradiction = _get_contradiction_or_404(db, contradiction_id, workspace_id)

    if contradiction.status != "unresolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 모순입니다.",
        )
    _check_meeting_not_recording(db, contradiction)
    
    updated = contradiction_crud.dismiss_contradiction(db, contradiction_id)
    return _to_contradiction_schema(db, updated)

# 변경 요약 초안 조회
@router.get("/{contradiction_id}/change-summary", response_model=ChangeSummaryDraftSchema)
def get_change_summary_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_contradiction_or_404(db, contradiction_id, workspace_id)

    draft = contradiction_crud.get_change_summary_draft(db, contradiction_id)
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="변경 요약 초안을 찾을 수 없습니다.",
        )
    return ChangeSummaryDraftSchema.model_validate(draft)

# 모순 되돌리기 ("유지"로 처리된 것만 다시 미해결로)
@router.post("/{contradiction_id}/reopen", response_model=ContradictionSchema)
def reopen_contradiction_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    contradiction = _get_contradiction_or_404(db, contradiction_id, workspace_id)

    if contradiction.status == "unresolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 미해결 상태입니다.",
        )

    resolution = contradiction_crud.get_resolution(db, contradiction_id)
    if not resolution or resolution.resolution_type != "keep_reference":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="'유지'로 처리된 모순만 되돌릴 수 있습니다.",
        )

    updated = contradiction_crud.reopen_contradiction(db, contradiction_id)
    return _to_contradiction_schema(db, updated)


# 잘못 감지된 모순 내용 수정
@router.patch("/{contradiction_id}", response_model=ContradictionSchema)
def update_contradiction_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    request: ContradictionUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    contradiction = _get_contradiction_or_404(db, contradiction_id, workspace_id)

    if request.statement_text_snapshot is None and request.reference_text_snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 내용이 없습니다.",
        )
    if contradiction.status != "unresolved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 모순입니다.",
        )
    _check_meeting_not_recording(db, contradiction)

    updated = contradiction_crud.update_contradiction_snapshots(
        db, contradiction_id,
        statement_text_snapshot=request.statement_text_snapshot,
        reference_text_snapshot=request.reference_text_snapshot,
    )
    return _to_contradiction_schema(db, updated)