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
from backend.graphs.contradiction_graph import run_contradiction_detection
from backend.graphs.meeting_postprocess_graph import run_meeting_postprocess
from backend.services.stt_stream_client import SttStreamClient

router = APIRouter(tags=["Meetings (Realtime)"])

# TODO: NAS 연결되면 이 경로/저장 로직을 NAS 저장으로 교체 (다른 업로드 로직과 동일한 임시 조치)
MEETING_RECORDING_STORAGE_DIR = Path("data/uploads/recordings")

# asyncio 이벤트 루프는 진행 중인 태스크를 약한 참조로만 들고 있어서, 반환값을 아무 데도
# 저장하지 않으면 참조가 없어져 완료 전에 GC될 수 있다(asyncio 공식 문서 경고).
# 여기 담아두고 완료 시 스스로 discard하게 해서 방지한다.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


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

    # recording -> processing 전이를 원자적으로 시도한다. /end REST 호출(end_meeting_api)이
    # 근접한 시점에 같은 전이를 시도할 수 있으므로, 실제로 이긴 쪽만 후처리를 예약해야 중복 실행을 막는다.
    transitioned = meeting_crud.try_transition_meeting_status(
        db, meeting_id, from_status="recording", to_status="processing",
        ended_at=ended_at, duration_ms=duration_ms,
    )
    if transitioned is None:
        return

    # 요약/결정사항/할 일 생성(LLM 호출 포함)은 오래 걸릴 수 있어 백그라운드로 돌린다.
    # run_meeting_postprocess는 동기 함수라 to_thread로 감싸서 이벤트 루프를 막지 않게 한다.
    _spawn_background_task(asyncio.to_thread(
        run_meeting_postprocess,
        meeting_id=str(meeting_id),
        workspace_id=str(meeting.workspace_id),
        category_id=str(meeting.category_id),
    ))


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
    meeting_id: uuid.UUID, workspace_id: uuid.UUID, category_id: uuid.UUID, next_index: int,
) -> None:
    async for data in stt_client.receive():
        msg_type = data.get("type")

        if msg_type == "partial":
            await websocket.send_json(data)

        elif msg_type == "final":
            for seg in data.get("final", {}).get("segments", []):
                segment_row = meeting_crud.add_segment(
                    db,
                    meeting_id=meeting_id,
                    content=seg.get("text", ""),
                    start_ms=int(seg["start"] * 1000),
                    end_ms=int(seg["end"] * 1000),
                    segment_index=next_index,
                    speaker_label=seg.get("speaker"),
                )
                next_index += 1

                # 발화 하나 저장될 때마다 모순 탐지를 백그라운드로 실행.
                # run_contradiction_detection도 동기 함수라 to_thread로 감싼다.
                statement_text = (segment_row.content or "").strip()
                if statement_text:
                    _spawn_background_task(asyncio.to_thread(
                        run_contradiction_detection,
                        workspace_id=str(workspace_id),
                        category_id=str(category_id),
                        source_type="meeting_segment",
                        statement_text=statement_text,
                        meeting_segment_id=str(segment_row.id),
                    ))
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
        _relay_stt_to_frontend(
            websocket, stt_client, db, meeting_id,
            meeting.workspace_id, meeting.category_id, next_index,
        )
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