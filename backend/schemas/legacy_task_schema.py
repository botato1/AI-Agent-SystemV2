# 업무 추출 / 업무 관리 관련 스키마
from typing import Optional, Literal
from pydantic import BaseModel, Field


# 업무 상태 값 (v1 호환용 — task_router.py / chat_service.py의 STATUS_MAP과 맞물려 있음)
# NOTE: type_schema.py의 신규 TaskStatus(Re:Call v3, "open"/"cancelled" 등)와
# 이름은 같지만 값 구성이 다른 별개의 타입이라 Legacy 접두사로 구분한다.
LegacyTaskStatus = Literal["todo", "in_progress", "done", "delayed"]

# 업무 우선순위 값 (v1 호환용)
LegacyTaskPriority = Literal["high", "medium", "low"]


# 할 일 하나의 구조 (v1 호환용)
class TaskItemSchema(BaseModel):
    task_id: str
    task: str
    assignee: Optional[str] = None
    deadline: Optional[str] = None
    status: LegacyTaskStatus = "todo"
    priority: LegacyTaskPriority = "medium"
    room_id: Optional[str] = None
    document_id: Optional[str] = None
    created_at: Optional[str] = None


# 업무 직접 생성 요청 구조 (v1 호환 — task_router.py POST /api/tasks)
class TaskCreateRequest(BaseModel):
    task: str = Field(..., min_length=1)
    assignee: Optional[str] = None
    deadline: Optional[str] = None
    status: LegacyTaskStatus = "todo"
    priority: LegacyTaskPriority = "medium"
    room_id: Optional[str] = None
    document_id: Optional[str] = None


# 업무 상태 변경 요청 구조 (v1 호환 — task_router.py PATCH /api/tasks/{task_id}/status)
class TaskStatusUpdateRequest(BaseModel):
    status: LegacyTaskStatus


# 업무 우선순위 변경 요청 구조 (v1 호환 — task_router.py PATCH /api/tasks/{task_id}/priority)
class TaskPriorityUpdateRequest(BaseModel):
    priority: LegacyTaskPriority