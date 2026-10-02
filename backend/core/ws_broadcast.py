# backend/core/ws_broadcast.py

"""워크스페이스 단위 WS 커넥션 관리 + 브로드캐스트 공통 로직.

meeting_list_ws_router.py / notification_ws_router.py에서 쓰던 패턴
(workspace_id -> list[WebSocket] dict, broadcast, run_coroutine_threadsafe
동기 래퍼)이 contradiction/task/room/member에도 똑같이 필요해서 클래스로
뽑았다. 각 리소스별 ws_router 파일은 이 클래스를 인스턴스화해서 쓰고,
자기 리소스의 티켓 검증/엔드포인트 등록만 담당한다.
"""

import asyncio
import uuid

from fastapi import WebSocket

from backend.core.main_loop import get_main_loop


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
        (asyncio.run()으로 별도 루프를 만들지 않음 - meeting_list_ws_router.py 리뷰 반영)."""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.broadcast(workspace_id, payload), get_main_loop(),
            )
            future.result(timeout=5)
        except Exception as e:
            print(f"[ws_broadcast:{self._label}] 동기 컨텍스트 push 실패: {repr(e)}")
