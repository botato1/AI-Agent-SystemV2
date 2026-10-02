# backend/routers/task_router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member, resolve_category
from backend.core.security import create_resource_ws_ticket
from backend.db.session import get_db
from backend.db.crud import meeting_crud, room_crud
from backend.routers.task_ws_router import broadcast_task_event_sync
from backend.schemas.task_schema import (
    TaskCreateRequest,
    TaskStatusUpdateRequest,
    TaskPriorityUpdateRequest,
    TaskUpdateRequest,
    TaskResponse,
    TaskListResponse,
)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/tasks", tags=["Tasks"])


class TaskWsTicketResponse(BaseModel):
    ws_ticket: str


# 워크스페이스 할 일 목록 실시간 연결용 WS 티켓 발급
@router.get("/stream/ticket", response_model=TaskWsTicketResponse)
def get_task_ws_ticket(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    ticket = create_resource_ws_ticket("task", current_user_id, str(workspace_id))
    return TaskWsTicketResponse(ws_ticket=ticket)


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
    category_id: UUID | None = Query(None),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    include_done = status == "all"
    items = meeting_crud.list_tasks(db, workspace_id, include_done=include_done, category_id=category_id)
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

    category = resolve_category(db, workspace_id, request.category_id)

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
    broadcast_task_event_sync(workspace_id, {"event": "task_created", "task_id": str(item.id)})
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
    broadcast_task_event_sync(workspace_id, {"event": "task_updated", "task_id": str(task_id)})
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
    broadcast_task_event_sync(workspace_id, {"event": "task_updated", "task_id": str(task_id)})
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
    if "category_id" in update_fields:
        if update_fields["category_id"] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="category_id는 null로 지울 수 없습니다.",
            )
        category = resolve_category(db, workspace_id, update_fields["category_id"])
        update_fields["category_id"] = category.id
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 내용이 없습니다.",
        )

    item = meeting_crud.update_task(db, task_id, **update_fields)
    broadcast_task_event_sync(workspace_id, {"event": "task_updated", "task_id": str(task_id)})
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
    broadcast_task_event_sync(workspace_id, {"event": "task_deleted", "task_id": str(task_id)})