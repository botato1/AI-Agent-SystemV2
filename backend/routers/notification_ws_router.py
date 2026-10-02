# backend/routers/notification_ws_router.py

"""워크스페이스 단위 알림 실시간 이벤트 push

create_notification() 호출부가 전부 동기(def) 함수/백그라운드 작업 안이라서
동기 래퍼를 같이 둔다.

[리뷰 반영] meeting_list_ws_router.py와 함께, backend/core/ws_broadcast.py의
WorkspaceBroadcastChannel/make_workspace_stream_router로 공용화 - 블로킹
future.result(timeout=5) 래퍼 퇴역."""

from backend.core.security import verify_notification_ws_ticket
from backend.core.ws_broadcast import make_workspace_stream_router

router, _channel = make_workspace_stream_router(
    label="notification",
    path="/api/workspaces/{workspace_id}/notifications/stream",
    verify_fn=verify_notification_ws_ticket,
    tags=["Notifications (Realtime)"],
)
broadcast_notification_event = _channel.broadcast
broadcast_notification_event_sync = _channel.broadcast_sync
