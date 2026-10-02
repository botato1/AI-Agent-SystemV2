# backend/routers/room_ws_router.py

"""채팅방 실시간 메시지 push — 내 파트

REST(POST /messages)로 저장은 그대로 하고, 저장 직후 같은 방에 붙어있는
다른 연결에 새 메시지를 그대로 push한다. 클라이언트→서버 방향 데이터는
없음(전송은 여전히 REST) — 이 WS는 순수 구독(수신 전용) 채널이다.

[리뷰 반영] 다른 6개 리소스(contradiction/task/room_list/member/meeting_list/
notification)는 workspace_id로 스코프되고 "워크스페이스 멤버인가"로 검증해서
make_workspace_stream_router로 통일했는데, 여기는 room_id로 스코프되고
"그 room_id가 실제 존재하는가"로 검증해서 경로/검증 방식이 다르다 - 억지로
make_workspace_stream_router에 끼워맞추지 않고, 실제로 공통인 연결 등록/
해제/브로드캐스트 부분만 WorkspaceBroadcastChannel을 재사용해 중복을 줄인다
(키가 workspace_id든 room_id든 그냥 uuid.UUID라 그대로 재사용 가능)."""

import uuid

from fastapi import APIRouter, Query, WebSocket
from jose import JWTError

from backend.core.security import verify_room_ws_ticket
from backend.core.ws_broadcast import WorkspaceBroadcastChannel
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import room_crud
from backend.db.session import SessionLocal

router = APIRouter(tags=["Rooms (Realtime)"])

_channel = WorkspaceBroadcastChannel("room")
broadcast_room_event = _channel.broadcast


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
    _channel.register(room_id, websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    finally:
        _channel.unregister(room_id, websocket)
        try:
            await websocket.close()
        except Exception:
            pass
