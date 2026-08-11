# backend/routers/task_router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import meeting_crud, room_crud
from backend.schemas.task_schema import (
    TaskCreateRequest,
    TaskStatusUpdateRequest,
    TaskPriorityUpdateRequest,
    TaskUpdateRequest,
    TaskResponse,
    TaskListResponse,
)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/tasks", tags=["Tasks"])


def _get_task_or_404(db: Session, task_id: UUID, workspace_id: UUID):
    item = meeting_crud.get_task(db, task_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="할 일을 찾을 수 없습니다.",
        )
    return item


# 워크스페이스 내 할 일 목록 조회 (기본: 진행 중인 것만, status=all이면 완료 포함 전체)
@router.get("", response_model=TaskListResponse)
def get_task_list(
    workspace_id: UUID,
    status: str | None = Query(None),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    include_done = status == "all"
    items = meeting_crud.list_tasks(db, workspace_id, include_done=include_done)
    return TaskListResponse(
        tasks=[TaskResponse.model_validate(i) for i in items]
    )


# 할 일 직접 생성 (meeting_id=None)
@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    workspace_id: UUID,
    request: TaskCreateRequest,
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

    item = meeting_crud.create_task(
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
    return TaskResponse.model_validate(item)


# 할 일 단건 조회
@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    workspace_id: UUID,
    task_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    item = _get_task_or_404(db, task_id, workspace_id)
    return TaskResponse.model_validate(item)


# 할 일 상태 변경
@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status_api(
    workspace_id: UUID,
    task_id: UUID,
    request: TaskStatusUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_task_or_404(db, task_id, workspace_id)

    item = meeting_crud.update_task_status(db, task_id, request.status)
    return TaskResponse.model_validate(item)


# 할 일 우선순위 변경
@router.patch("/{task_id}/priority", response_model=TaskResponse)
def update_task_priority_api(
    workspace_id: UUID,
    task_id: UUID,
    request: TaskPriorityUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_task_or_404(db, task_id, workspace_id)

    item = meeting_crud.update_task_priority(db, task_id, request.priority)
    return TaskResponse.model_validate(item)

# 할 일 상세 수정 (제목/설명/담당자/마감일/우선순위/상태를 한 번에)
@router.patch("/{task_id}", response_model=TaskResponse)
def update_task_api(
    workspace_id: UUID,
    task_id: UUID,
    request: TaskUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_task_or_404(db, task_id, workspace_id)

    update_fields = request.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 내용이 없습니다.",
        )

    item = meeting_crud.update_task(db, task_id, **update_fields)
    return TaskResponse.model_validate(item)


# 할 일 삭제
@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_api(
    workspace_id: UUID,
    task_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_task_or_404(db, task_id, workspace_id)

    meeting_crud.delete_task(db, task_id)