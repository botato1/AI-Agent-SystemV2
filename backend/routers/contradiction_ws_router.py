# backend/routers/contradiction_ws_router.py

"""워크스페이스 단위 모순(contradiction) 목록 실시간 이벤트 push.
공용 핸들러는 backend/core/ws_broadcast.py의 make_workspace_stream_router 참조
(리뷰 반영 - 이전엔 4개 리소스 ws_router.py가 거의 동일한 핸들러를 복붙했었음)."""

from backend.core.security import verify_contradiction_ws_ticket
from backend.core.ws_broadcast import make_workspace_stream_router

router, _channel = make_workspace_stream_router(
    label="contradiction",
    path="/api/workspaces/{workspace_id}/contradictions/stream",
    verify_fn=verify_contradiction_ws_ticket,
    tags=["Contradictions (Realtime)"],
)
broadcast_contradiction_event = _channel.broadcast
broadcast_contradiction_event_sync = _channel.broadcast_sync
