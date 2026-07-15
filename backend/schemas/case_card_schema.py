# 내부 사건 카드 구조
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field

CasePriority = Literal["low", "medium", "high", "urgent"]       # 사건 카드 우선 순위
CaseStatus = Literal["open", "reviewing", "done", "archived"]   # 사건 카드의 진행 상태(새로 열린 사건, 검토 중, 처리 완료, 보관됨)

# 사건 카드 전체 구조
class CaseCardSchema(BaseModel):
    id: str                                     # 사건 카드 ID
    room_id: Optional[str] = None               # v1 호환용 : 채팅방 ID
    conversation_id: str                        # v2 : 사건방 ID    
    client_name: Optional[str] = None           # 의뢰인 이름
    case_category: Optional[str] = None         # 사건 종류(ex. 계약 분쟁, 임대차, 손해배상 등)
    consultation_date: Optional[str] = None     # 상담일
    summary: Optional[str] = None               # 사건 요약
    related_document_ids: list[str] = Field(default_factory=list)               # 연결된 문서 ID 목록
    related_legal_refs: list[dict[str, Any]] = Field(default_factory=list)      # 관련 법령/판례/계약서 조항 근거 목록
    action_items: list[dict[str, Any]] = Field(default_factory=list)            # 이 사건에서 해야 할 조치 목록
    priority: CasePriority = "medium"           # 사건 우선순위
    status: CaseStatus = "open"                 # 사건 진행상태
    created_at: str                             # 생성시간      
    updated_at: str                             # 수정시간

# 사건 카드 생성 요청 구조
class CaseCardCreateRequest(BaseModel):
    room_id: str                                # v1 호환용 : 채팅방 ID
    conversation_id: Optional[str] = None       # v2 : 사건방 ID
    document_ids: list[str] = Field(default_factory=list)      # 사건 카드에 연결할 문서 ID 목록

# 사건 카드 수정 요청 구조
class CaseCardUpdateRequest(BaseModel):
    case_card_id: str                 # 수정할 사건 카드 ID
    summary: Optional[str] = None     # 사건 요약
    action_items: Optional[list[dict[str, Any]]] = None     # 사건에서 해야 할 조치 목록
    priority: Optional[CasePriority] = None                 # 사건 우선순위
    status: Optional[CaseStatus] = None                     # 사건 진행상태

# 사건 카드 응답 구조
class CaseCardResponse(BaseModel):
    status: str                                             # 성공/실패 상태
    case_card: Optional[CaseCardSchema] = None              # 사건 카드 데이터
    error: Optional[str] = None                             # 에러 메시지