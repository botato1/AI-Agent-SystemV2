# backend/services/stt_stream_client.py

import json
import os
from typing import Any, AsyncIterator, Optional

import websockets

# 8001 실시간 STT WebSocket 서버 주소
STT_STREAM_BASE_URL = os.getenv("STT_STREAM_BASE_URL", "ws://61.81.98.82:8002")


class SttStreamClient:
    """
    8001 실시간 STT WebSocket 세션 하나를 감싸는 클라이언트.

    session_id로 우리 meeting_id를 그대로 넘긴다.
    입력 오디오는 PCM16LE/16kHz/mono 원시 바이트여야 한다 (8001 쪽 요구사항,
    변환은 프론트엔드가 담당하므로 여기서는 그대로 릴레이만 한다).
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._ws: Optional[Any] = None

    async def connect(self) -> None:
        url = f"{STT_STREAM_BASE_URL}/api/ws/stt/{self.session_id}"
        self._ws = await websockets.connect(url, max_size=None)

    async def send_audio(self, chunk: bytes) -> None:
        await self._ws.send(chunk)

    async def send_end(self) -> None:
        await self._ws.send("end")

    async def receive(self) -> AsyncIterator[dict]:
        """8001이 보내는 JSON 메시지를 하나씩 반환한다 (partial/final/session_end)."""
        async for raw_message in self._ws:
            yield json.loads(raw_message)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None