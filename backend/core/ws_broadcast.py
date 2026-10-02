# backend/core/ws_broadcast.py

"""워크스페이스 단위 WS 커넥션 관리 + 브로드캐스트 공통 로직.

meeting_list_ws_router.py / notification_ws_router.py에서 쓰던 패턴
(workspace_id -> list[WebSocket] dict, broadcast, run_coroutine_threadsafe
동기 래퍼)이 contradiction/task/room/member에도 똑같이 필요해서 클래스로
뽑았다.

[수정 - 리뷰 반영] 거기서 한 발 더 나아가, contradiction/task/room_list/member
ws_router.py 4개 파일이 "티켓 검증 -> workspace_id 일치 확인 -> 티켓 소모 ->
멤버십 확인 -> accept -> register -> receive 루프 -> unregister/close"로
토씨만 다르고 완전히 동일한 ~55줄짜리 핸들러를 복붙하고 있었다. 검증 함수와
채널만 바뀌는 부분이라 make_workspace_stream_router()로 뽑아서, 각 리소스별
ws_router.py는 이제 자기 리소스의 티켓 검증 함수 하나만 넘기면 된다.
"""

import asyncio
import uuid
from typing import Callable

from fastapi import APIRouter, Query, WebSocket
from jose import JWTError

from backend.core.main_loop import get_main_loop
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import workspace_crud
from backend.db.session import SessionLocal


class WorkspaceBroadcastChannel:
    def __init__(self, label: str):
        self._label = label
        self._connections: dict[uuid.UUID, list[WebSocket]] = {}

    def register(self, workspace_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections.setdefault(workspace_id, []).append(websocket)

    def unregister(self, workspace_id: uuid.UUID, websocket: WebSocket) -> None:
        connections = self._connections.get(workspace_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                self._connections.pop(workspace_id, None)

    async def broadcast(self, workspace_id: uuid.UUID, payload: dict) -> None:
        connections = self._connections.get(workspace_id)
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
            self._connections.pop(workspace_id, None)

    def broadcast_sync(self, workspace_id: uuid.UUID, payload: dict) -> None:
        """동기(def) 라우트 핸들러/백그라운드 스레드에서 호출하기 위한 래퍼.
        WebSocket 연결이 묶여있는 메인 이벤트 루프 위에서 스레드-안전하게 실행한다
        (asyncio.run()으로 별도 루프를 만들지 않음 - meeting_list_ws_router.py 리뷰 반영).

        [수정 - 리뷰 반영] 예전엔 future.result(timeout=5)로 완료를 기다렸는데,
        이 함수가 전부 생성/수정/삭제 같은 동기 REST 라우트 핸들러 안에서
        호출되다 보니 WS 클라이언트 하나가 느리거나 메인 루프가 잠깐 바쁘기만
        해도 그 HTTP 요청 자체가 최대 5초 묶여버린다. 브로드캐스트는 응답에
        영향을 주지 않아도 되는 부가 효과(최악의 경우 클라이언트가 다음
        재연결/폴백 때 받음)라 fire-and-forget으로 바꾸고, 실패는 콜백에서
        로그만 남긴다."""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.broadcast(workspace_id, payload), get_main_loop(),
            )
        except Exception as e:
            print(f"[ws_broadcast:{self._label}] 브로드캐스트 예약 실패: {repr(e)}")
            return

        def _log_if_failed(f) -> None:
            exc = f.exception()
            if exc is not None:
                print(f"[ws_broadcast:{self._label}] 비동기 push 실패: {repr(exc)}")

        future.add_done_callback(_log_if_failed)


def make_workspace_stream_router(
    *, label: str, path: str, verify_fn: Callable[[str], dict], tags: list[str],
    channel: "WorkspaceBroadcastChannel | None" = None,
) -> tuple[APIRouter, "WorkspaceBroadcastChannel"]:
    """contradiction/task/room_list/member가 공유하는 WS 스트림 엔드포인트를
    조립한다. 리소스별로 다른 건 티켓 검증 함수와 경로/태그뿐이라 그것만
    주입받는다. 반환된 router를 main.py에 등록하고, channel의
    broadcast/broadcast_sync를 mutation 지점에서 호출하면 된다.

    channel을 안 넘기면 여기서 새로 만든다(기존 동작, task/room/member처럼
    router 모듈이 채널을 전담 소유해도 되는 경우). 이미 만들어둔 채널이 있으면
    (예: contradiction - graphs/judgment 레이어가 직접 push해야 해서 채널을
    backend/core/contradiction_events.py에 둠) 그걸 그대로 쓰도록 넘길 수
    있다 - 안 그러면 "router가 만든 채널"과 "core가 만든 채널"이 따로 놀아서
    WS는 한쪽에 register되는데 push는 다른 쪽에서 나가는 버그가 생긴다."""
    channel = channel or WorkspaceBroadcastChannel(label)
    router = APIRouter(tags=tags)

    @router.websocket(path)
    async def stream_ws(websocket: WebSocket, workspace_id: uuid.UUID, ticket: str = Query(...)):
        try:
            payload = verify_fn(ticket)
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
        channel.register(workspace_id, websocket)
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
        finally:
            channel.unregister(workspace_id, websocket)
            try:
                await websocket.close()
            except Exception:
                pass

    return router, channel
