# backend/routers/document_ws_router.py

"""워크스페이스 단위 문서/그래프 실시간 이벤트 push

채팅방(room_ws_router.py)과 동일한 패턴. 업로드/삭제/분석 완료는 REST 요청
안에서 동기적으로 끝나므로, 그 지점에서 바로 broadcast_document_event를
호출한다. 유사도 계산만 백그라운드 스레드에서 돌아서, 그쪽만 동기 래퍼
(broadcast_document_event_sync)를 통해 이벤트 루프를 새로 열어 push한다.
"""

import asyncio
import uuid

from fastapi import APIRouter, Query, WebSocket
from jose import JWTError

from backend.core.security import verify_document_ws_ticket
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import workspace_crud
from backend.db.session import SessionLocal

router = APIRouter(tags=["Documents (Realtime)"])

_DOCUMENT_CONNECTIONS: dict[uuid.UUID, list[WebSocket]] = {}


async def broadcast_document_event(workspace_id: uuid.UUID, payload: dict) -> None:
    connections = _DOCUMENT_CONNECTIONS.get(workspace_id)
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
        _DOCUMENT_CONNECTIONS.pop(workspace_id, None)


def broadcast_document_event_sync(workspace_id: uuid.UUID, payload: dict) -> None:
    """백그라운드 스레드(BackgroundTasks의 동기 함수)에서 호출하기 위한 래퍼.
    그 컨텍스트엔 실행 중인 이벤트 루프가 없어 asyncio.run으로 새로 연다."""
    try:
        asyncio.run(broadcast_document_event(workspace_id, payload))
    except Exception as e:
        print(f"[document_ws_router] 동기 컨텍스트 push 실패: {repr(e)}")


@router.websocket("/api/workspaces/{workspace_id}/documents/stream")
async def document_stream_ws(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    ticket: str = Query(...),
):
    try:
        payload = verify_document_ws_ticket(ticket)
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
    _DOCUMENT_CONNECTIONS.setdefault(workspace_id, []).append(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    finally:
        connections = _DOCUMENT_CONNECTIONS.get(workspace_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                _DOCUMENT_CONNECTIONS.pop(workspace_id, None)
        try:
            await websocket.close()
        except Exception:
            pass