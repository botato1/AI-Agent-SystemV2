# backend/routers/meeting_list_ws_router.py

"""워크스페이스 단위 회의 목록 실시간 이벤트 push

document_ws_router.py와 동일한 패턴. 회의 상태가 바뀌는 REST 엔드포인트
(start/upload/schedule/end/begin/pause/resume)가 전부 동기(def) 함수라서,
그 안에서 바로 부를 수 있게 broadcast_meeting_list_event_sync를 함께 둔다.
"""

import asyncio
import uuid

from fastapi import APIRouter, Query, WebSocket
from jose import JWTError

from backend.core.security import verify_meeting_list_ws_ticket
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import workspace_crud
from backend.db.session import SessionLocal

router = APIRouter(tags=["Meetings (Realtime List)"])

_MEETING_LIST_CONNECTIONS: dict[uuid.UUID, list[WebSocket]] = {}


async def broadcast_meeting_list_event(workspace_id: uuid.UUID, payload: dict) -> None:
    connections = _MEETING_LIST_CONNECTIONS.get(workspace_id)
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
        _MEETING_LIST_CONNECTIONS.pop(workspace_id, None)


def broadcast_meeting_list_event_sync(workspace_id: uuid.UUID, payload: dict) -> None:
    """동기(def) 라우트 핸들러 안에서 호출하기 위한 래퍼.
    그 컨텍스트엔 실행 중인 이벤트 루프가 없어 asyncio.run으로 새로 연다."""
    try:
        asyncio.run(broadcast_meeting_list_event(workspace_id, payload))
    except Exception as e:
        print(f"[meeting_list_ws_router] 동기 컨텍스트 push 실패: {repr(e)}")


@router.websocket("/api/workspaces/{workspace_id}/meetings/stream")
async def meeting_list_stream_ws(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    ticket: str = Query(...),
):
    try:
        payload = verify_meeting_list_ws_ticket(ticket)
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
    _MEETING_LIST_CONNECTIONS.setdefault(workspace_id, []).append(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    finally:
        connections = _MEETING_LIST_CONNECTIONS.get(workspace_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                _MEETING_LIST_CONNECTIONS.pop(workspace_id, None)
        try:
            await websocket.close()
        except Exception:
            pass