# backend/routers/meeting_list_ws_router.py

"""워크스페이스 단위 회의 목록 실시간 이벤트 push

회의 상태가 바뀌는 REST 엔드포인트(start/upload/schedule/end/begin/pause/resume)가
전부 동기(def) 함수라서, 그 안에서 바로 부를 수 있게 broadcast_meeting_list_event_sync를
함께 둔다.

[리뷰 반영] 원래 이 파일이 "asyncio.run() 대신 run_coroutine_threadsafe" 패턴의
원본이었고, contradiction/task/room_list/member 4개 리소스가 이 패턴을 그대로
베껴 쓰다가 backend/core/ws_broadcast.py의 WorkspaceBroadcastChannel/
make_workspace_stream_router로 공용화됐다. 정작 패턴의 원조인 이 파일과
notification_ws_router.py는 여전히 구버전(블로킹 future.result(timeout=5))을
쓰고 있어서, 똑같이 공용 구현으로 옮겨 블로킹 래퍼를 완전히 퇴역시킨다."""

from backend.core.security import verify_meeting_list_ws_ticket
from backend.core.ws_broadcast import make_workspace_stream_router

router, _channel = make_workspace_stream_router(
    label="meeting_list",
    path="/api/workspaces/{workspace_id}/meetings/stream",
    verify_fn=verify_meeting_list_ws_ticket,
    tags=["Meetings (Realtime List)"],
)
broadcast_meeting_list_event = _channel.broadcast
broadcast_meeting_list_event_sync = _channel.broadcast_sync
