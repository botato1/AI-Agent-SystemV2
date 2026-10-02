# backend/routers/room_list_ws_router.py

"""워크스페이스 단위 채팅방(room) 목록 실시간 이벤트 push.
room_ws_router.py(채팅방 안 메시지 스트림)와는 별개 - 이건 "방 목록 자체"의
생성/삭제/수정 이벤트를 다룬다.

공용 핸들러는 backend/core/ws_broadcast.py의 make_workspace_stream_router 참조
(리뷰 반영 - 이전엔 4개 리소스 ws_router.py가 거의 동일한 핸들러를 복붙했었음)."""

from backend.core.security import verify_room_list_ws_ticket
from backend.core.ws_broadcast import make_workspace_stream_router

router, _channel = make_workspace_stream_router(
    label="room_list",
    path="/api/workspaces/{workspace_id}/rooms/stream",
    verify_fn=verify_room_list_ws_ticket,
    tags=["Rooms List (Realtime)"],
)
broadcast_room_list_event = _channel.broadcast
broadcast_room_list_event_sync = _channel.broadcast_sync
