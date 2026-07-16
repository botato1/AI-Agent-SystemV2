# 업무 추출 / 업무 관리 관련 스키마
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field


# 업무 상태 값 (v1 호환용 — task_router.py / chat_service.py의 STATUS_MAP과 맞물려 있음)
TaskStatus = Literal["todo", "in_progress", "done", "delayed"]

# 업무 우선순위 값 (v1 호환용)
TaskPriority = Literal["high", "medium", "low"]

# v2 법률 할일 전용 상태/우선순위 값 (v1 TaskStatus/TaskPriority와 값 구성이 달라 별도 선언)
LegalActionStatus = Literal["todo", "in_progress", "done", "blocked"]
LegalActionPriority = Literal["low", "medium", "high", "urgent"]


# 할 일 하나의 구조 (v1 호환용)
class TaskItemSchema(BaseModel):
    task_id: str
    task: str
    assignee: Optional[str] = None
    deadline: Optional[str] = None
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    room_id: Optional[str] = None
    document_id: Optional[str] = None
    created_at: Optional[str] = None


# TODO: v2 법률 할일 생성용 구조 : 추후 할일 생성 기능 추가 시 확정
class LegalActionItemSchema(BaseModel):
    task_id: Optional[str] = None               # 할 일 ID
    task: str                                   # 할 일 내용
    reason: Optional[str] = None                # 할 일 생성 이유/근거

    status: LegalActionStatus = "todo"          # 처리 상태
    priority: LegalActionPriority = "medium"    # 우선순위

    room_id: Optional[str] = None               # v1 호환용 : 채팅방 ID
    conversation_id: Optional[str] = None       # v2 : 사건방 ID

    document_id: Optional[str] = None           # 연결 문서 ID
    source_document_id: Optional[str] = None    # 이 할 일이 나온 원본 문서 ID
    source_clause: Optional[str] = None         # 이 할 일이 나온 조항

    related_legal_refs: list[dict[str, Any]] = Field(default_factory=list)      # 관련 법령/판례/계약서 조항 근거 목록

    risk_level: Optional[LegalActionPriority] = None        # 법률 위험도
    created_at: Optional[str] = None                        # 생성시간
    updated_at: Optional[str] = None                        # 수정시간


# 요약 + 할 일 추출 결과 구조
class TaskResultSchema(BaseModel):
    summary: Optional[str] = None
    tasks: list[TaskItemSchema] = Field(default_factory=list)
    action_items: list[LegalActionItemSchema] = Field(default_factory=list)


# 업무 직접 생성 요청 구조 (v1 호환 — task_router.py POST /api/tasks)
class TaskCreateRequest(BaseModel):
    task: str = Field(..., min_length=1)
    assignee: Optional[str] = None
    deadline: Optional[str] = None
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    room_id: Optional[str] = None
    document_id: Optional[str] = None


# 업무 상태 변경 요청 구조 (v1 호환 — task_router.py PATCH /api/tasks/{task_id}/status)
class TaskStatusUpdateRequest(BaseModel):
    status: TaskStatus


# 업무 우선순위 변경 요청 구조 (v1 호환 — task_router.py PATCH /api/tasks/{task_id}/priority)
class TaskPriorityUpdateRequest(BaseModel):
    priority: TaskPriority