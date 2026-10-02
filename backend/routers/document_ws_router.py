# backend/routers/document_ws_router.py

"""워크스페이스 단위 문서/그래프 실시간 이벤트 push

[리뷰 반영] broadcast_document_event_sync()가 asyncio.run()으로 매번 새
이벤트 루프를 열고 있었다 - 실제 WS 연결이 묶여있는 메인 uvicorn 루프와
다른 루프라서, document_router.py의 문서 삭제·worktree_router.py의
워크트리/파일 삭제처럼 동기 라우트 핸들러(워커 스레드에서 실행)에서
호출될 때 ws.send_json()이 잘못된 루프에서 실행돼 예외가 나고,
broadcast_document_event의 except Exception이 멀쩡한 연결을 죽은 걸로
오판해서 지워버릴 수 있었다 - meeting_list/notification/contradiction 등
5개 리소스에서 고친 것과 동일한 버그. make_workspace_stream_router/
WorkspaceBroadcastChannel로 옮겨서 run_coroutine_threadsafe 기반 구현으로
통일한다."""

from backend.core.security import verify_document_ws_ticket
from backend.core.ws_broadcast import make_workspace_stream_router

router, _channel = make_workspace_stream_router(
    label="document",
    path="/api/workspaces/{workspace_id}/documents/stream",
    verify_fn=verify_document_ws_ticket,
    tags=["Documents (Realtime)"],
)
broadcast_document_event = _channel.broadcast
broadcast_document_event_sync = _channel.broadcast_sync
