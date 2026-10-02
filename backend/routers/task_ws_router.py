# backend/routers/task_ws_router.py

"""워크스페이스 단위 할 일(task) 목록 실시간 이벤트 push.
공용 핸들러는 backend/core/ws_broadcast.py의 make_workspace_stream_router 참조
(리뷰 반영 - 이전엔 4개 리소스 ws_router.py가 거의 동일한 핸들러를 복붙했었음)."""

from backend.core.security import verify_task_ws_ticket
from backend.core.ws_broadcast import make_workspace_stream_router

router, _channel = make_workspace_stream_router(
    label="task",
    path="/api/workspaces/{workspace_id}/tasks/stream",
    verify_fn=verify_task_ws_ticket,
    tags=["Tasks (Realtime)"],
)
broadcast_task_event = _channel.broadcast
broadcast_task_event_sync = _channel.broadcast_sync
