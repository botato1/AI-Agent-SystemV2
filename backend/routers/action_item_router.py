# backend/routers/action_item_router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import meeting_crud, room_crud
from backend.schemas.action_item_schema import (
    ActionItemCreateRequest,
    ActionItemStatusUpdateRequest,
    ActionItemPriorityUpdateRequest,
    ActionItemResponse,
    ActionItemListResponse,
)


router = APIRouter(prefix="/api/workspaces/{workspace_id}/action-items", tags=["Action Items"])


def _get_action_item_or_404(db: Session, action_item_id: UUID, workspace_id: UUID):
    item = meeting_crud.get_action_item(db, action_item_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="할 일을 찾을 수 없습니다.",
        )
    return item


# 워크스페이스 내 진행 중인 할 일 목록 조회
@router.get("", response_model=ActionItemListResponse)
def get_action_item_list(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    items = meeting_crud.list_open_action_items(db, workspace_id)
    return ActionItemListResponse(
        action_items=[ActionItemResponse.model_validate(i) for i in items]
    )


# 할 일 직접 생성 (meeting_id=None)
@router.post("", response_model=ActionItemResponse, status_code=status.HTTP_201_CREATED)
def create_action_item(
    workspace_id: UUID,
    request: ActionItemCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    category = room_crud.get_default_category(db, workspace_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="워크스페이스의 기본 카테고리를 찾을 수 없습니다.",
        )

    item = meeting_crud.create_action_item(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        title=request.title,
        description=request.description,
        assignee_id=request.assignee_id,
        assignee_label=request.assignee_label,
        priority=request.priority,
        due_at=request.due_at,
        status="open",
        created_by=UUID(current_user_id),
    )
    return ActionItemResponse.model_validate(item)


# 할 일 단건 조회
@router.get("/{action_item_id}", response_model=ActionItemResponse)
def get_action_item(
    workspace_id: UUID,
    action_item_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    item = _get_action_item_or_404(db, action_item_id, workspace_id)
    return ActionItemResponse.model_validate(item)


# 할 일 상태 변경
@router.patch("/{action_item_id}/status", response_model=ActionItemResponse)
def update_action_item_status_api(
    workspace_id: UUID,
    action_item_id: UUID,
    request: ActionItemStatusUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_action_item_or_404(db, action_item_id, workspace_id)

    item = meeting_crud.update_action_item_status(db, action_item_id, request.status)
    return ActionItemResponse.model_validate(item)


# 할 일 우선순위 변경
@router.patch("/{action_item_id}/priority", response_model=ActionItemResponse)
def update_action_item_priority_api(
    workspace_id: UUID,
    action_item_id: UUID,
    request: ActionItemPriorityUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_action_item_or_404(db, action_item_id, workspace_id)

    item = meeting_crud.update_action_item_priority(db, action_item_id, request.priority)
    return ActionItemResponse.model_validate(item)


# 할 일 삭제
@router.delete("/{action_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_action_item_api(
    workspace_id: UUID,
    action_item_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_action_item_or_404(db, action_item_id, workspace_id)

    meeting_crud.delete_action_item(db, action_item_id)