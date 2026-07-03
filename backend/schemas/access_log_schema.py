# 접근 로그 구조
from typing import Optional, Literal
from pydantic import BaseModel

# 접근 대상 종류
ResourceType = Literal[
    "conversation",         # 사건방/채팅방
    "document",             # 업로드 문서
    "message",              # 채팅 메시지
    "case_card",            # 사건 카드
]

# 수행한 행동 종류
AccessAction = Literal[
    "view",                 # 조회
    "create",               # 생성
    "update",               # 수정
    "delete",               # 삭제
    "decrypt",              # 복호화
    "download",             # 다운로드
]

# 접근 결과
AccessResult = Literal["success", "denied", "error"]        # 성공/권한없음/오류

# 접근 로그 생성용 구조
class AccessLogCreateSchema(BaseModel):
    user_id: str                        # 접근한 사용자 ID
    resource_type: ResourceType         # 접근 대상 종류
    resource_id: str                    # 접근 대상 ID
    action: AccessAction                # 수행한 행동
    result: AccessResult                # 성공/거부/에러 여부

    reason: Optional[str] = None        # 접근/실패 사유
    ip_address: Optional[str] = None    # 사용자 ip 주소
    user_agent: Optional[str] = None    # 브라우저/클라이언트 정보

    created_at: Optional[str] = None    # 로그 생성 시간

# DB에서 조회한 접근 로그 구조
class AccessLogSchema(AccessLogCreateSchema):
    id: int