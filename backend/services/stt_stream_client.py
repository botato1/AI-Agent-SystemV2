import json
import os
from typing import Any, AsyncIterator, Optional
from urllib.parse import quote

import websockets

STT_STREAM_BASE_URL = os.getenv("STT_STREAM_BASE_URL", "ws://61.81.98.82:8002")

class SttStreamClient:
    def __init__(
        self,
        session_id: str,
        participant_name: Optional[str] = None,
        attendees: Optional[list[str]] = None,
    ):
        self.session_id = session_id
        self.participant_name = participant_name
        self.attendees = attendees
        self._ws: Optional[Any] = None

    async def connect(self) -> None:
        url = f"{STT_STREAM_BASE_URL}/api/ws/stt/{self.session_id}"
        params = []
        if self.participant_name:
            params.append(f"participant_name={quote(self.participant_name)}")
        if self.attendees:
            params.append(f"attendees={quote(','.join(self.attendees))}")
        if params:
            url += "?" + "&".join(params)
        self._ws = await websockets.connect(url, max_size=None)