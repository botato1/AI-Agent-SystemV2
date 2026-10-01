# backend/routers/notification_ws_router.py

"""워크스페이스 단위 알림 실시간 이벤트 push

meeting_list_ws_router.py와 동일한 패턴. create_notification() 호출부가
전부 동기(def) 함수/백그라운드 작업 안이라서 동기 래퍼를 같이 둔다.

[리뷰 반영] asyncio.run() 대신 run_coroutine_threadsafe로 메인 이벤트 루프
위에서 직접 실행 - meeting_list_ws_router.py 상단 docstring 참조.
"""

import asyncio
import uuid

from fastapi import APIRouter, Query, WebSocket
from jose import JWTError

from backend.core.main_loop import get_main_loop
from backend.core.security import verify_notification_ws_ticket
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import workspace_crud
from backend.db.session import SessionLocal

router = APIRouter(tags=["Notifications (Realtime)"])

_NOTIFICATION_CONNECTIONS: dict[uuid.UUID, list[WebSocket]] = {}


async def broadcast_notification_event(workspace_id: uuid.UUID, payload: dict) -> None:
    connections = _NOTIFICATION_CONNECTIONS.get(workspace_id)
    if not connections:
        return
    stale: list[WebSocket] = []
    for ws in list(connections):
        try:
            await ws.send_json(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        connections.remove(ws)
    if not connections:
        _NOTIFICATION_CONNECTIONS.pop(workspace_id, None)


def broadcast_notification_event_sync(workspace_id: uuid.UUID, payload: dict) -> None:
    """동기 컨텍스트(def 라우트 핸들러, 백그라운드 작업)에서 호출하기 위한 래퍼.
    WebSocket 연결이 묶여있는 메인 이벤트 루프 위에서 스레드-안전하게 실행한다."""
    try:
        future = asyncio.run_coroutine_threadsafe(
            broadcast_notification_event(workspace_id, payload), get_main_loop(),
        )
        future.result(timeout=5)
    except Exception as e:
        print(f"[notification_ws_router] 동기 컨텍스트 push 실패: {repr(e)}")


@router.websocket("/api/workspaces/{workspace_id}/notifications/stream")
async def notification_stream_ws(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    ticket: str = Query(...),
):
    try:
        payload = verify_notification_ws_ticket(ticket)
    except JWTError:
        await websocket.close(code=4401)
        return

    if payload.get("workspace_id") != str(workspace_id):
        await websocket.close(code=4401)
        return

    if not consume_ticket(payload["jti"], payload["exp"]):
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        member = workspace_crud.get_membership(db, workspace_id, uuid.UUID(payload["sub"]))
    finally:
        db.close()
    if not member:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    _NOTIFICATION_CONNECTIONS.setdefault(workspace_id, []).append(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    finally:
        connections = _NOTIFICATION_CONNECTIONS.get(workspace_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                _NOTIFICATION_CONNECTIONS.pop(workspace_id, None)
        try:
            await websocket.close()
        except Exception:
            pass
