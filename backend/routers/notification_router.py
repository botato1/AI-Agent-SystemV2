# backend/routers/notification_router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import notification_crud
from backend.schemas.notification_schema import (
    NotificationListResponse, NotificationSchema,
    NotificationPreferencesSchema, NotificationPreferencesUpdateRequest,
)

preferences_router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["Notifications"])

router = APIRouter(prefix="/api/workspaces/{workspace_id}/notifications", tags=["Notifications"])


def _get_notification_or_404(db: Session, notification_id: UUID, workspace_id: UUID, user_id: str):
    notification = notification_crud.get_notification(db, notification_id)
    if (
        not notification
        or notification.workspace_id != workspace_id
        or str(notification.user_id) != user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="알림을 찾을 수 없습니다.",
        )
    return notification


# 알림 목록 조회
@router.get("", response_model=NotificationListResponse)
def get_notification_list(
    workspace_id: UUID,
    unread_only: bool = Query(default=False),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    items = notification_crud.list_notifications(
        db, UUID(current_user_id), workspace_id, unread_only=unread_only,
    )
    return NotificationListResponse(
        notifications=[NotificationSchema.model_validate(i) for i in items]
    )


# 알림 읽음 처리
@router.patch("/{notification_id}/read", response_model=NotificationSchema)
def mark_notification_read(
    workspace_id: UUID,
    notification_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    notification = _get_notification_or_404(db, notification_id, workspace_id, current_user_id)

    notification_crud.mark_read(db, notification_id)
    db.refresh(notification)
    return NotificationSchema.model_validate(notification)

@preferences_router.get("/notification-preferences", response_model=NotificationPreferencesSchema)
def get_notification_preferences_api(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    prefs = notification_crud.get_notification_preferences(db, workspace_id, UUID(current_user_id))
    return NotificationPreferencesSchema(**prefs)


@preferences_router.patch("/notification-preferences", response_model=NotificationPreferencesSchema)
def update_notification_preferences_api(
    workspace_id: UUID,
    request: NotificationPreferencesUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    updates = request.model_dump(exclude_none=True)
    prefs = notification_crud.update_notification_preferences(
        db, workspace_id, UUID(current_user_id), updates,
    )
    return NotificationPreferencesSchema(**prefs)