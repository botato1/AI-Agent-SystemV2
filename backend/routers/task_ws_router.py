# backend/routers/task_ws_router.py

"""워크스페이스 단위 할 일(task) 목록 실시간 이벤트 push.
meeting_list_ws_router.py와 동일한 패턴 - WorkspaceBroadcastChannel 사용."""

import uuid

from fastapi import APIRouter, Query, WebSocket
from jose import JWTError

from backend.core.security import verify_task_ws_ticket
from backend.core.ws_broadcast import WorkspaceBroadcastChannel
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import workspace_crud
from backend.db.session import SessionLocal

router = APIRouter(tags=["Tasks (Realtime)"])

_channel = WorkspaceBroadcastChannel("task")
broadcast_task_event = _channel.broadcast
broadcast_task_event_sync = _channel.broadcast_sync


@router.websocket("/api/workspaces/{workspace_id}/tasks/stream")
async def task_stream_ws(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    ticket: str = Query(...),
):
    try:
        payload = verify_task_ws_ticket(ticket)
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
    _channel.register(workspace_id, websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    finally:
        _channel.unregister(workspace_id, websocket)
        try:
            await websocket.close()
        except Exception:
            pass
