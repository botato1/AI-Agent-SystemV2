# backend/routers/contradiction_router.py

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import contradiction_crud, file_crud, notification_crud, workspace_crud
from backend.db.modules import Decision
from backend.graphs.change_summary_graph import run_change_summary_generation
from backend.schemas.contradiction_schema import (
    ContradictionSchema,
    ContradictionListResponse,
    ContradictionResolveRequest,
    ChangeSummaryDraftSchema,
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

    if source_name and excerpt:
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

    schema = ContradictionSchema.model_validate(contradiction)
    schema.reference_source_name = source_name
    schema.display_message = display_message
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