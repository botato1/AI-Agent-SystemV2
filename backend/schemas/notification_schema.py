# backend/schemas/notification_schema.py

"""
알림(notifications) 관련 Pydantic 스키마를 정의한다.

access_logs는 기능 명세에 따라 MVP에서 제외한다.

서비스 계층에서 다음 관계를 검증해야 한다.
- notifications.workspace_id가 사용자가 속한 워크스페이스인지 확인
- room_id가 있으면 해당 room이 workspace_id에 속하는지 확인
- ref_id가 있으면 ref_type에 해당하는 데이터가 실제로 존재하는지 확인
- 읽음 처리 시 is_read와 read_at을 함께 갱신

TODO:
- 알림 생성, 조회, 읽음 처리 API의 요청·응답 스키마는
  관련 라우터 구현 시 별도로 정의
- ref_type의 값 목록은 아직 확정되지 않았으므로 str로 유지
- ref_id가 가리키는 대상 종류가 확정되면 ref_type을 Literal로 제한
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from backend.schemas.common_schema import ORMBaseSchema
from backend.schemas.type_schema import NotificationType


# =============================================================================
# Re:Call: notifications
# =============================================================================

class NotificationSchema(ORMBaseSchema):
    """
    사용자 알림 하나를 표현한다.

    notifications 테이블에는 updated_at과 deleted_at 컬럼이 없으므로
    created_at만 직접 선언한다.
    """

    id: UUID
    user_id: UUID
    workspace_id: UUID

    type: NotificationType

    title: Optional[str] = Field(
        default=None,
        max_length=200,
    )
    message: Optional[str] = None

    ref_type: Optional[str] = Field(
        default=None,
        max_length=30,
    )
    ref_id: Optional[UUID] = None
    room_id: Optional[UUID] = None

    is_read: bool
    read_at: Optional[datetime] = None

    created_at: datetime