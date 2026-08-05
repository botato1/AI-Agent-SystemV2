# backend/routers/meeting_ws_router.py

import asyncio
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, Query, WebSocket
from jose import JWTError
from sqlalchemy.orm import Session

from backend.core.security import verify_ws_ticket
from backend.core.ws_ticket_store import consume_ticket
from backend.db.crud import meeting_crud, file_crud, contradiction_crud, notification_crud, workspace_crud, auth_crud
from backend.db.session import get_db, SessionLocal
from backend.graphs.contradiction_graph import run_contradiction_detection
from backend.services.stt_stream_client import SttStreamClient
from backend.services import judgment_service, meeting_service

router = APIRouter(tags=["Meetings (Realtime)"])

MEETING_RECORDING_STORAGE_DIR = Path("storage/uploads/recordings")

# asyncio 이벤트 루프는 진행 중인 태스크를 약한 참조로만 들고 있어서, 반환값을 아무 데도
# 저장하지 않으면 참조가 없어져 완료 전에 GC될 수 있다(asyncio 공식 문서 경고).
# 여기 담아두고 완료 시 스스로 discard하게 해서 방지한다.
_BACKGROUND_TASKS: set[asyncio.Task] = set()

_PAUSED_STREAMS: dict[uuid.UUID, asyncio.Event] = {}
_ACTIVE_CONNECTIONS: dict[uuid.UUID, int] = {}

def _register_connection(meeting_id: uuid.UUID) -> None:
    _ACTIVE_CONNECTIONS[meeting_id] = _ACTIVE_CONNECTIONS.get(meeting_id, 0) + 1

def _unregister_connection(meeting_id: uuid.UUID) -> bool:
    """마지막 연결이면 True — 이때만 회의 종료 처리해야 한다."""
    remaining = _ACTIVE_CONNECTIONS.get(meeting_id, 1) - 1
    if remaining <= 0:
        _ACTIVE_CONNECTIONS.pop(meeting_id, None)
        return True
    _ACTIVE_CONNECTIONS[meeting_id] = remaining
    return False

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

def _notify_contradiction_detected(workspace_id: uuid.UUID, contradiction_id: str, display_message: str) -> None:
    """모순 감지 시 워크스페이스 멤버들에게 알림을 남긴다 (알림 설정 on/off 반영)."""
    db = SessionLocal()
    try:
        for member, _user in workspace_crud.list_members(db, workspace_id):
            if not notification_crud.is_notification_enabled(
                db, workspace_id, member.user_id, "contradiction_detected",
            ):
                continue
            notification_crud.create_notification(
                db, user_id=member.user_id, workspace_id=workspace_id,
                type="contradiction_detected", title="모순 감지",
                message=display_message,
                ref_type="contradiction", ref_id=uuid.UUID(contradiction_id),
            )
    finally:
        db.close()

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

    await asyncio.to_thread(_notify_contradiction_detected, workspace_id, contradiction_id, display_message)

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
    async with processing_lock:
        await _detect_and_push_contradiction(
            websocket, send_lock,
            workspace_id, category_id,
            statement_text, meeting_segment_id,
        )
        judgment_result = await asyncio.to_thread(
            judgment_service.run_judgment_pipeline,
            workspace_id=str(workspace_id),
            category_id=str(category_id),
            source_type="meeting_segment",
            statement_text=statement_text,
            meeting_segment_id=meeting_segment_id,
            session_meeting_id=str(meeting_id),
        )
        if judgment_result:
            try:
                async with send_lock:
                    await websocket.send_json({
                        "type": "contradiction_alert",
                        "contradiction_id": judgment_result["contradiction_id"],
                        "statement_text": statement_text,
                        "display_message": judgment_result["message"],
                        "source": "decision",
                        "judgment_case": judgment_result.get("judgment_case"),
                        "actions": judgment_result.get("actions", []),
                    })
            except Exception as e:
                print(f"[meeting_ws_router] decision 모순 알림 전송 실패: {repr(e)}")


def _open_recording_file(meeting_id: uuid.UUID, participant_name: str | None = None, offset_ms: int = 0):
    MEETING_RECORDING_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if participant_name:
        path = MEETING_RECORDING_STORAGE_DIR / f"{meeting_id}_{participant_name}_{offset_ms}.pcm"
    else:
        path = MEETING_RECORDING_STORAGE_DIR / f"{meeting_id}.pcm"
    return open(path, "ab")

def _merge_individual_recordings(meeting_id: uuid.UUID) -> None:
    """각자 PC 모드: 참가자별 PCM 파일을 회의 시작 기준 오프셋만큼 무음 패딩 후 파형 합산해서
    single_device 모드와 동일한 {meeting_id}.pcm 하나로 만든다. 겹치는 구간은 클리핑 처리."""
    participant_files = sorted(MEETING_RECORDING_STORAGE_DIR.glob(f"{meeting_id}_*_*.pcm"))
    if not participant_files:
        return

    SAMPLE_RATE = 16000
    streams: list[tuple[int, np.ndarray]] = []
    max_len = 0

    for path in participant_files:
        try:
            offset_ms = int(path.stem.rsplit("_", 1)[-1])
        except ValueError:
            offset_ms = 0
        offset_samples = int(offset_ms * SAMPLE_RATE / 1000)

        raw = path.read_bytes()
        raw = raw[: len(raw) - (len(raw) % 2)]  # 홀수 바이트 꼬리 제거
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.int32)

        streams.append((offset_samples, samples))
        max_len = max(max_len, offset_samples + len(samples))

    if max_len == 0:
        return

    mixed = np.zeros(max_len, dtype=np.int32)
    for offset_samples, samples in streams:
        mixed[offset_samples: offset_samples + len(samples)] += samples

    mixed = np.clip(mixed, -32768, 32767).astype(np.int16)

    output_path = MEETING_RECORDING_STORAGE_DIR / f"{meeting_id}.pcm"
    output_path.write_bytes(mixed.tobytes())

def _extract_stt_confidence(seg: dict) -> float | None:
    avg_logprob = seg.get("avg_logprob")
    if avg_logprob is not None:
        return round(math.exp(avg_logprob), 4)
    confident = seg.get("confident")
    if confident is not None:
        return 1.0 if confident else 0.5
    return None

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

    if meeting.recording_mode == "individual":
        _merge_individual_recordings(meeting_id)

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
        meeting_service.run_meeting_postprocess_and_notify,
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

_MEETING_SPEAKER_MAPS: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
_VIEWER_CONNECTIONS: dict[uuid.UUID, list[WebSocket]] = {}

async def _broadcast_to_viewers(meeting_id: uuid.UUID, data: dict) -> None:
    viewers = _VIEWER_CONNECTIONS.get(meeting_id)
    if not viewers:
        return
    for viewer_ws in list(viewers):
        try:
            await viewer_ws.send_json(data)
        except Exception:
            pass  # 끊긴 뷰어는 자기 쪽에서 정리됨


async def _relay_stt_to_frontend(
    websocket: WebSocket, stt_client: SttStreamClient, db: Session,
    meeting_id: uuid.UUID, workspace_id: uuid.UUID, category_id: uuid.UUID,
    meeting_started_by: uuid.UUID, send_lock: asyncio.Lock, processing_lock: asyncio.Lock,
    speaker_name_to_user_id: dict[str, uuid.UUID],
) -> None:
    async for data in stt_client.receive():
        if isinstance(data, (bytes, bytearray)):
            # 통화(voice) 음성 프레임 - 그대로 프론트로 중계 ([1바이트 발신자 슬롯][PCM16LE])
            async with send_lock:
                await websocket.send_bytes(data)
            continue

        msg_type = data.get("type")

        if msg_type == "partial":
            async with send_lock:
                await websocket.send_json(data)
            await _broadcast_to_viewers(meeting_id, data)

        elif msg_type == "final":
            is_remote = bool(data.get("remote"))
            for seg in data.get("final", {}).get("segments", []):
                resolved_speaker = _resolve_speaker_label(db, meeting_id, seg.get("speaker"))
                seg["speaker"] = resolved_speaker
                speaker_user_id = speaker_name_to_user_id.get(resolved_speaker) if resolved_speaker else None
                seg["speaker_user_id"] = str(speaker_user_id) if speaker_user_id else None

                if is_remote:
                    continue  # 다른 참가자 연결에서 이미 저장·분석됨 - 화면 표시만 하고 저장은 스킵

                try:
                    segment_row = meeting_crud.add_segment_safe(
                        db,
                        meeting_id=meeting_id,
                        content=seg.get("text", ""),
                        start_ms=int(seg["start"] * 1000),
                        end_ms=int(seg["end"] * 1000),
                        speaker_label=resolved_speaker,
                        speaker_user_id=speaker_user_id,
                        stt_confidence=_extract_stt_confidence(seg),
                    )
                except Exception as e:
                    db.rollback()
                    print(f"[meeting_ws_router] 세그먼트 저장 실패: {repr(e)}")
                    continue

                statement_text = (segment_row.content or "").strip()
                if statement_text:
                    _spawn_background_task(_process_segment_analysis(
                        websocket, send_lock, processing_lock,
                        workspace_id, category_id,
                        statement_text, str(segment_row.id),
                        meeting_id, meeting_started_by,
                    ))
            async with send_lock:
                await websocket.send_json(data)
            await _broadcast_to_viewers(meeting_id, data)

        elif msg_type == "session_end":
            async with send_lock:
                await websocket.send_json(data)
            await _broadcast_to_viewers(meeting_id, data)
            return

        else:
            # voice_ready 등 새로운/알 수 없는 메시지 타입도 일단 그대로 프론트에 전달
            async with send_lock:
                await websocket.send_json(data)
            await _broadcast_to_viewers(meeting_id, data)


@router.websocket("/api/workspaces/{workspace_id}/meetings/{meeting_id}/stream")
async def meeting_stream_ws(
    websocket: WebSocket,
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    ticket: str = Query(...),
    voice: int = Query(0),
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

    if payload.get("view_only"):
        _VIEWER_CONNECTIONS.setdefault(meeting_id, []).append(websocket)
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
        finally:
            viewers = _VIEWER_CONNECTIONS.get(meeting_id)
            if viewers and websocket in viewers:
                viewers.remove(websocket)
                if not viewers:
                    _VIEWER_CONNECTIONS.pop(meeting_id, None)
            try:
                await websocket.close()
            except Exception:
                pass
        return

    participant_name = None
    attendee_names: list[str] | None = None
    speaker_name_to_user_id: dict[str, uuid.UUID] = {}
    if meeting.recording_mode == "individual":
        user = auth_crud.get_user_by_id(db, uuid.UUID(payload["sub"]))
        participant_name = user.display_name if user else payload["sub"]
        speaker_name_to_user_id = _MEETING_SPEAKER_MAPS.setdefault(meeting_id, {})
        if user and participant_name:
            speaker_name_to_user_id[participant_name] = user.id
    else:
        # single_device(한 공간에서): 참석자가 별도로 설정돼 있으면 그 사람들만,
        # 아니면(설정 안 했으면) 워크스페이스 멤버 전체를 후보로 삼아 그중
        # 목소리 등록된 사람만 "닫힌 집합"으로 넘긴다. 아무도 없으면 자동감지(auto) 폴백.
        attendee_rows = meeting_crud.get_attendees(db, meeting_id)
        if attendee_rows:
            candidate_user_ids = [user.id for _, user in attendee_rows]
        else:
            candidate_user_ids = [
                member.user_id for member, _ in workspace_crud.list_members(db, meeting.workspace_id)
            ]

        names = []
        for user_id in candidate_user_ids:
            profile = auth_crud.get_voice_profile(db, user_id)
            if profile:
                names.append(profile.speaker_name)
                speaker_name_to_user_id[profile.speaker_name] = user_id
        attendee_names = names or None

    stt_client = SttStreamClient(
        session_id=str(meeting_id), participant_name=participant_name, attendees=attendee_names,
        voice=bool(voice) and meeting.recording_mode == "individual",
    )
    try:
        await stt_client.connect()
    except Exception:
        await websocket.close(code=1011)
        return

    offset_ms = 0
    if participant_name and meeting.started_at:
        offset_ms = max(0, int((datetime.now(timezone.utc) - meeting.started_at).total_seconds() * 1000))
    recording_file = _open_recording_file(meeting_id, participant_name, offset_ms)

    _register_connection(meeting_id)
    paused_event = _PAUSED_STREAMS.get(meeting_id)
    if paused_event is None:
        paused_event = asyncio.Event()
        _PAUSED_STREAMS[meeting_id] = paused_event
    send_lock = asyncio.Lock()
    processing_lock = asyncio.Lock()

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
            meeting.workspace_id, meeting.category_id,
            meeting.started_by, send_lock, processing_lock,
            speaker_name_to_user_id,
        )
    )
    try:
        done, pending = await asyncio.wait(
            {frontend_task, stt_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    finally:
        is_last = _unregister_connection(meeting_id)
        if is_last:
            _PAUSED_STREAMS.pop(meeting_id, None)
            _MEETING_SPEAKER_MAPS.pop(meeting_id, None)
        recording_file.close()
        await stt_client.close()
        if is_last:
            _finalize_meeting_if_recording(db, meeting_id)
        try:
            await websocket.close()
        except Exception:
            pass