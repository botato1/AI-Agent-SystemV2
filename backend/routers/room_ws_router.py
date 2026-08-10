# backend/routers/room_ws_router.py

"""채팅방 실시간 메시지 push — 내 파트

REST(POST /messages)로 저장은 그대로 하고, 저장 직후 같은 방에 붙어있는
다른 연결에 새 메시지를 그대로 push한다. 클라이언트→서버 방향 데이터는
없음(전송은 여전히 REST) — 이 WS는 순수 구독(수신 전용) 채널이다.
"""

import uuid

from fastapi import APIRouter, Query, WebSocket
from jose import JWTError

from backend.core.security import verify_room_ws_ticket
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import room_crud
from backend.db.session import SessionLocal

router = APIRouter(tags=["Rooms (Realtime)"])

_ROOM_CONNECTIONS: dict[uuid.UUID, list[WebSocket]] = {}


async def broadcast_room_event(room_id: uuid.UUID, payload: dict) -> None:
    connections = _ROOM_CONNECTIONS.get(room_id)
    if not connections:
        return
    stale: list[WebSocket] = []
    for ws in connections:
        try:
            await ws.send_json(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        connections.remove(ws)
    if not connections:
        _ROOM_CONNECTIONS.pop(room_id, None)


@router.websocket("/api/workspaces/{workspace_id}/rooms/{room_id}/stream")
async def room_stream_ws(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    room_id: uuid.UUID,
    ticket: str = Query(...),
):
    try:
        payload = verify_room_ws_ticket(ticket)
    except JWTError:
        await websocket.close(code=4401)
        return

    if payload.get("room_id") != str(room_id):
        await websocket.close(code=4401)
        return

    if not consume_ticket(payload["jti"], payload["exp"]):
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        room = room_crud.get_room_by_id(db, room_id, workspace_id)
    finally:
        db.close()
    if not room:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    _ROOM_CONNECTIONS.setdefault(room_id, []).append(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    finally:
        connections = _ROOM_CONNECTIONS.get(room_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                _ROOM_CONNECTIONS.pop(room_id, None)
        try:
            await websocket.close()
        except Exception:
            pass
