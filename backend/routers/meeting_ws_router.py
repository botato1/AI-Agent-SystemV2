# backend/routers/meeting_ws_router.py

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, WebSocket
from jose import JWTError
from sqlalchemy.orm import Session

from backend.core.security import verify_ws_ticket
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import meeting_crud
from backend.db.session import get_db
from backend.services.stt_stream_client import SttStreamClient

router = APIRouter(tags=["Meetings (Realtime)"])

# TODO: NAS 연결되면 이 경로/저장 로직을 NAS 저장으로 교체 (다른 업로드 로직과 동일한 임시 조치)
MEETING_RECORDING_STORAGE_DIR = Path("data/uploads/recordings")


def _open_recording_file(meeting_id: uuid.UUID):
    MEETING_RECORDING_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = MEETING_RECORDING_STORAGE_DIR / f"{meeting_id}.pcm"
    return open(path, "ab")


def _finalize_meeting_if_recording(db: Session, meeting_id: uuid.UUID) -> None:
    """WS 세션이 어떤 이유로든 끝났을 때, 아직 recording 상태면 자동으로 마무리한다."""
    meeting = meeting_crud.get_meeting(db, meeting_id)
    if not meeting or meeting.status != "recording":
        return

    ended_at = datetime.now(timezone.utc)
    duration_ms = (
        int((ended_at - meeting.started_at).total_seconds() * 1000)
        if meeting.started_at else None
    )
    meeting_crud.update_meeting_status(
        db, meeting_id, status="processing", ended_at=ended_at, duration_ms=duration_ms,
    )


async def _relay_frontend_to_stt(websocket: WebSocket, stt_client: SttStreamClient, recording_file) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return

        chunk = message.get("bytes")
        if chunk is not None:
            recording_file.write(chunk)
            await stt_client.send_audio(chunk)
            continue

        text = message.get("text")
        if text == "end":
            await stt_client.send_end()


async def _relay_stt_to_frontend(
    websocket: WebSocket, stt_client: SttStreamClient, db: Session,
    meeting_id: uuid.UUID, next_index: int,
) -> None:
    async for data in stt_client.receive():
        msg_type = data.get("type")

        if msg_type == "partial":
            await websocket.send_json(data)

        elif msg_type == "final":
            for seg in data.get("final", {}).get("segments", []):
                meeting_crud.add_segment(
                    db,
                    meeting_id=meeting_id,
                    content=seg.get("text", ""),
                    start_ms=int(seg["start"] * 1000),
                    end_ms=int(seg["end"] * 1000),
                    segment_index=next_index,
                    speaker_label=seg.get("speaker"),
                )
                next_index += 1
                # TODO(승주): final 세그먼트 저장 직후 모순 탐지 파이프라인 호출 지점
            await websocket.send_json(data)

        elif msg_type == "session_end":
            await websocket.send_json(data)
            return


@router.websocket("/api/workspaces/{workspace_id}/meetings/{meeting_id}/stream")
async def meeting_stream_ws(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    ticket: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        payload = verify_ws_ticket(ticket)
    except JWTError:
        await websocket.close(code=4401)
        return

    if payload.get("meeting_id") != str(meeting_id):
        await websocket.close(code=4401)
        return

    if not consume_ticket(payload["jti"], payload["exp"]):
        await websocket.close(code=4401)
        return

    meeting = meeting_crud.get_meeting(db, meeting_id)
    if not meeting or meeting.workspace_id != workspace_id:
        await websocket.close(code=4404)
        return
    if meeting.status != "recording":
        await websocket.close(code=4409)
        return

    await websocket.accept()

    stt_client = SttStreamClient(session_id=str(meeting_id))
    try:
        await stt_client.connect()
    except Exception:
        await websocket.close(code=1011)
        return

    recording_file = _open_recording_file(meeting_id)
    next_index = len(meeting_crud.get_segments(db, meeting_id))

    frontend_task = asyncio.create_task(
        _relay_frontend_to_stt(websocket, stt_client, recording_file)
    )
    stt_task = asyncio.create_task(
        _relay_stt_to_frontend(websocket, stt_client, db, meeting_id, next_index)
    )

    try:
        done, pending = await asyncio.wait(
            {frontend_task, stt_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    finally:
        recording_file.close()
        await stt_client.close()
        _finalize_meeting_if_recording(db, meeting_id)
        try:
            await websocket.close()
        except Exception:
            pass