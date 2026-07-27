# backend/routers/meeting_ws_router.py

import asyncio
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query, WebSocket
from jose import JWTError
from sqlalchemy.orm import Session

from backend.core.security import verify_ws_ticket
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import meeting_crud, file_crud, contradiction_crud
from backend.db.session import get_db, SessionLocal
from backend.graphs.contradiction_graph import run_contradiction_detection
from backend.graphs.meeting_postprocess_graph import run_meeting_postprocess
from backend.services.stt_stream_client import SttStreamClient
from backend.services import judgment_service

router = APIRouter(tags=["Meetings (Realtime)"])

# TODO: NAS 연결되면 이 경로/저장 로직을 NAS 저장으로 교체 (다른 업로드 로직과 동일한 임시 조치)
MEETING_RECORDING_STORAGE_DIR = Path("data/uploads/recordings")

# asyncio 이벤트 루프는 진행 중인 태스크를 약한 참조로만 들고 있어서, 반환값을 아무 데도
# 저장하지 않으면 참조가 없어져 완료 전에 GC될 수 있다(asyncio 공식 문서 경고).
# 여기 담아두고 완료 시 스스로 discard하게 해서 방지한다.
_BACKGROUND_TASKS: set[asyncio.Task] = set()

_PAUSED_STREAMS: dict[uuid.UUID, asyncio.Event] = {}

def set_stream_paused(meeting_id: uuid.UUID, paused: bool) -> None:
    """REST pause/resume 엔드포인트가 현재 열려있는 WS 스트림에 신호를 보낼 때 사용.
    이 meeting_id로 열린 WS 연결이 없으면(아직 연결 전/이미 끊김) 아무 일도 안 함."""
    event = _PAUSED_STREAMS.get(meeting_id)
    if event is None:
        return
    if paused:
        event.set()
    else:
        event.clear()

def _spawn_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task

async def _detect_and_push_contradiction(
    websocket: WebSocket, send_lock: asyncio.Lock,
    workspace_id: uuid.UUID, category_id: uuid.UUID,
    statement_text: str, meeting_segment_id: str,
) -> None:
    """모순 감지를 실행하고, 실제로 발견되면 실시간 회의 화면(WS)으로 바로 push한다."""
    try:
        result = await asyncio.to_thread(
            run_contradiction_detection,
            workspace_id=str(workspace_id),
            category_id=str(category_id),
            source_type="meeting_segment",
            statement_text=statement_text,
            meeting_segment_id=meeting_segment_id,
        )
    except Exception as e:
        print(f"[meeting_ws_router] 모순 감지 실행 실패: {repr(e)}")
        return

    detected = result.get("detected_contradictions") or []
    saved_ids = result.get("saved_contradiction_ids") or []
    if not detected:
        return

    # 같은 발화에 대해 여러 개 감지될 수 있어(top-5 후보 각각 독립 판단) —
    # DB엔 다 저장되지만, 실시간 화면에는 확신도(confidence_score) 제일 높은
    # 것 하나만 보여준다. 근본 원인은 contradiction_detect.py(가동현) 쪽 수정 필요.
    pair_count = min(len(detected), len(saved_ids))
    best_index = max(range(pair_count), key=lambda i: detected[i]["confidence_score"])
    contradiction = detected[best_index]
    contradiction_id = saved_ids[best_index]

    source_name = None
    excerpt = ""
    reference_file_id = contradiction.get("reference_file_id")
    if reference_file_id:
        db = SessionLocal()
        try:
            file = file_crud.get_file(db, uuid.UUID(reference_file_id))
            source_name = file.original_filename if file else None

            saved_row = contradiction_crud.get_contradiction(db, uuid.UUID(contradiction_id))
            if saved_row and saved_row.reference_text_snapshot:
                excerpt = " ".join(saved_row.reference_text_snapshot.split())[:100]
        finally:
            db.close()

    if source_name and excerpt:
        display_message = f"'{statement_text}'라고 하셨는데, 기존 자료({source_name})의 '{excerpt}'와 다릅니다."
    elif excerpt:
        display_message = f"'{statement_text}'라고 하셨는데, 기존 자료의 '{excerpt}'와 다릅니다."
    else:
        display_message = f"'{statement_text}'라고 하셨는데, 기존 자료와 다릅니다."

    try:
        async with send_lock:
            await websocket.send_json({
                "type": "contradiction_alert",
                "contradiction_id": contradiction_id,
                "statement_text": statement_text,
                "reason": contradiction["reason"],
                "severity": contradiction["severity"],
                "confidence_score": contradiction["confidence_score"],
                "reference_source_name": source_name,
                "display_message": display_message,
            })
    except Exception as e:
        print(f"[meeting_ws_router] 모순 알림 전송 실패: {repr(e)}")

async def _process_segment_analysis(
    websocket: WebSocket, send_lock: asyncio.Lock, processing_lock: asyncio.Lock,
    workspace_id: uuid.UUID, category_id: uuid.UUID,
    statement_text: str, meeting_segment_id: str,
    meeting_id: uuid.UUID, meeting_started_by: uuid.UUID,
) -> None:
    """모순 감지 + 판단 파이프라인을 세그먼트 단위로 직렬 처리한다.
    둘 다 LLM 호출 동안 DB 커넥션을 물고 있어서, 여러 세그먼트가 동시에
    실행되면 커넥션 풀이 고갈된다 (업로드 음성 경로가 순차 처리하는 것과 같은 이유)."""
    async with processing_lock:
        await _detect_and_push_contradiction(
            websocket, send_lock,
            workspace_id, category_id,
            statement_text, meeting_segment_id,
        )
        await asyncio.to_thread(
            judgment_service.run_judgment_pipeline,
            workspace_id=str(workspace_id),
            category_id=str(category_id),
            source_type="meeting_segment",
            statement_text=statement_text,
            meeting_segment_id=meeting_segment_id,
            session_meeting_id=str(meeting_id),
        )


def _open_recording_file(meeting_id: uuid.UUID):
    MEETING_RECORDING_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = MEETING_RECORDING_STORAGE_DIR / f"{meeting_id}.pcm"
    return open(path, "ab")

def _extract_stt_confidence(seg: dict) -> float | None:
    """avg_logprob(로그 확률)을 0~1 범위 신뢰도 점수로 변환. 없으면 None."""
    avg_logprob = seg.get("avg_logprob")
    if avg_logprob is None:
        return None
    return round(math.exp(avg_logprob), 4)

def _resolve_speaker_label(db: Session, meeting_id: uuid.UUID, raw_label: str | None) -> str | None:
    """이 회의에 설정된 화자 매핑을 적용한다. PATCH /speakers가 다른 요청에서 커밋한
    최신 매핑을 확실히 읽기 위해 expire_all 후 재조회한다."""
    if not raw_label:
        return raw_label
    db.expire_all()
    meeting = meeting_crud.get_meeting(db, meeting_id)
    mapping = (meeting.speaker_labels or {}) if meeting else {}
    return mapping.get(raw_label, raw_label)

def _finalize_meeting_if_recording(db: Session, meeting_id: uuid.UUID) -> None:
    """WS 세션이 어떤 이유로든 끝났을 때, 아직 recording/paused 상태면 자동으로 마무리한다."""
    db.expire_all()  # REST pause/resume이 다른 세션에서 커밋한 최신 값을 확실히 읽기 위함
    meeting = meeting_crud.get_meeting(db, meeting_id)
    if not meeting or meeting.status not in ("recording", "paused"):
        return

    ended_at = datetime.now(timezone.utc)
    duration_ms = (
        max(0, int((ended_at - meeting.started_at).total_seconds() * 1000) - meeting.paused_duration_ms)
        if meeting.started_at else None
    )

    # recording/paused -> processing 전이를 원자적으로 시도한다. /end REST 호출(end_meeting_api)이
    # 근접한 시점에 같은 전이를 시도할 수 있으므로, 실제로 이긴 쪽만 후처리를 예약해야 중복 실행을 막는다.
    transitioned = meeting_crud.try_transition_meeting_status(
        db, meeting_id, from_status=meeting.status, to_status="processing",
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


async def _relay_frontend_to_stt(websocket: WebSocket, stt_client: SttStreamClient, recording_file, paused_event: asyncio.Event) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return

        chunk = message.get("bytes")
        if chunk is not None:
            if paused_event.is_set():
                continue  # 일시정지 중 — 저장/STT 전송 안 함
            recording_file.write(chunk)
            await stt_client.send_audio(chunk)
            continue

        text = message.get("text")
        if text == "end":
            await stt_client.send_end()


async def _relay_stt_to_frontend(
    websocket: WebSocket, stt_client: SttStreamClient, db: Session,
    meeting_id: uuid.UUID, workspace_id: uuid.UUID, category_id: uuid.UUID, next_index: int,
    meeting_started_by: uuid.UUID, send_lock: asyncio.Lock, processing_lock: asyncio.Lock,
) -> None:
    async for data in stt_client.receive():
        msg_type = data.get("type")

        if msg_type == "partial":
            async with send_lock:
                await websocket.send_json(data)
            
        elif msg_type == "final":
            for seg in data.get("final", {}).get("segments", []):
                resolved_speaker = _resolve_speaker_label(db, meeting_id, seg.get("speaker"))
                seg["speaker"] = resolved_speaker  # WS로 나가는 payload에도 반영
                try:
                    segment_row = meeting_crud.add_segment(
                        db,
                        meeting_id=meeting_id,
                        content=seg.get("text", ""),
                        start_ms=int(seg["start"] * 1000),
                        end_ms=int(seg["end"] * 1000),
                        segment_index=next_index,
                        speaker_label=resolved_speaker,
                        stt_confidence=_extract_stt_confidence(seg),
                    )
                    next_index += 1
                except Exception as e:
                    db.rollback()
                    print(f"[meeting_ws_router] 세그먼트 저장 실패: {repr(e)}")
                    continue

                # 발화 하나 저장될 때마다 모순 탐지를 실행하고, 실제로 발견되면 WS로 실시간 push한다.
                statement_text = (segment_row.content or "").strip()
                if statement_text:
                    # 모순감지+판단파이프라인은 processing_lock으로 직렬화 —
                    # 둘 다 LLM 호출 동안 DB 커넥션을 물고 있어서 동시 실행 시 풀 고갈됨.
                    _spawn_background_task(_process_segment_analysis(
                        websocket, send_lock, processing_lock,
                        workspace_id, category_id,
                        statement_text, str(segment_row.id),
                        meeting_id, meeting_started_by,
                    ))
            async with send_lock:
                await websocket.send_json(data)

        elif msg_type == "session_end":
            async with send_lock:
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

    # REST pause/resume 엔드포인트가 이 스트림에 신호를 보낼 수 있게 등록.
    # set()되면 오디오를 저장/전송하지 않고 버림 (일시정지 상태).
    paused_event = asyncio.Event()
    _PAUSED_STREAMS[meeting_id] = paused_event
    send_lock = asyncio.Lock()  # 여러 백그라운드 작업이 동시에 websocket.send_json 하는 것 방지
    processing_lock = asyncio.Lock()  # 세그먼트별 모순감지+판단파이프라인 직렬화 (DB 커넥션 풀 고갈 방지)

    # 이 등록 전(WS 핸드셰이크/STT 서버 연결 대기 중)에 /pause REST가 먼저
    # 처리됐을 수 있다 — 그 경우 set_stream_paused는 아직 없는 이벤트를 조용히
    # 무시하고 지나간다. 등록 직후 DB 상태를 다시 확인해 놓친 일시정지를 반영한다.
    db.expire_all()
    current_meeting = meeting_crud.get_meeting(db, meeting_id)
    if current_meeting and current_meeting.status == "paused":
        paused_event.set()

    frontend_task = asyncio.create_task(
        _relay_frontend_to_stt(websocket, stt_client, recording_file, paused_event)
    )
    stt_task = asyncio.create_task(
        _relay_stt_to_frontend(
            websocket, stt_client, db, meeting_id,
            meeting.workspace_id, meeting.category_id, next_index,
            meeting.started_by, send_lock, processing_lock,
        )
    )

    try:
        done, pending = await asyncio.wait(
            {frontend_task, stt_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    finally:
        _PAUSED_STREAMS.pop(meeting_id, None)
        recording_file.close()
        await stt_client.close()
        _finalize_meeting_if_recording(db, meeting_id)
        try:
            await websocket.close()
        except Exception:
            pass