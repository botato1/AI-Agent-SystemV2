from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from backend.schemas.task_schema import TaskItemSchema


class SourceSchema(BaseModel):
    # v1 RAG source 필드
    id: str
    title: Optional[str] = None
    source: str
    source_url: Optional[str] = None
    data_type: Optional[str] = None
    score: Optional[float] = None
    importance: Optional[int] = None
    created_at: Optional[str] = None
    tags: Optional[List[str]] = None
    
    # v2 법률/RAG source 필드
    document_id: Optional[str] = None
    page_number: Optional[int] = None
    clause: Optional[str] = None
    content: Optional[str] = None



class ChatResponseSchema(BaseModel):
    # v2 기준 사건방 ID
    conversation_id: Optional[str] = None

    # v1 호환용 채팅방 ID
    room_id: Optional[str] = None

    answer: str
    summary: Optional[str] = None

    # v1 호환
    tasks: List[TaskItemSchema] = Field(default_factory=list)

    # v2 법률 할일
    action_items: List[Dict[str, Any]] = Field(default_factory=list)

    # v2 법률 분석 결과
    legal_issues: List[str] = Field(default_factory=list)
    risk_clauses: List[Dict[str, Any]] = Field(default_factory=list)

    # RAG 근거
    sources: List[SourceSchema] = Field(default_factory=list)

    # v2 사건 카드
    case_card: Optional[Dict[str, Any]] = None

    graph_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None