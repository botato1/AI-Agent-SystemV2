# backend/routers/contradiction_router.py

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import contradiction_crud
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
        contradictions=[ContradictionSchema.model_validate(c) for c in items]
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
    return ContradictionSchema.model_validate(contradiction)


# 모순 해결
@router.post("/{contradiction_id}/resolve", response_model=ContradictionSchema)
def resolve_contradiction_api(
    workspace_id: uuid.UUID,
    contradiction_id: uuid.UUID,
    request: ContradictionResolveRequest,
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

    if request.resolution_type == "change_acknowledged":
        # TODO: LLM 기반 변경요약 실제 생성은 후속 작업 — 지금은 draft row만 pending 상태로 생성
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

    updated = contradiction_crud.get_contradiction(db, contradiction_id)
    return ContradictionSchema.model_validate(updated)


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
    return ContradictionSchema.model_validate(updated)


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