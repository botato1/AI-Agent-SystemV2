# backend/routers/meeting_router.py

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
import io
import wave
from sqlalchemy.orm import Session

from backend.core.security import create_ws_ticket
from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import meeting_crud, room_crud, file_crud, workspace_crud, contradiction_crud, auth_crud
from backend.modules.rag.document_loader import load_document
from backend.services import document_service, meeting_service
from backend.services.meeting_service import process_uploaded_audio_stt
from backend.modules.rag.chroma_client import MEETING_COLLECTION, search_hybrid
from backend.modules.judgment import agenda_reminder
from backend.db.modules import Meeting
from backend.routers import meeting_ws_router
from backend.schemas.task_schema import TaskResponse, TaskListResponse
from backend.schemas.meeting_schema import (
    MeetingStartRequest,
    MeetingResponse,
    MeetingListResponse,
    MeetingSegmentListResponse,
    MeetingSegmentResponse,
    DecisionListResponse,
    DecisionResponse,
    MeetingStartResponse,
    SpeakerLabelMappingRequest,
    MeetingTitleUpdateRequest,
    DecisionWithHistoryListResponse,
    DecisionWithHistoryResponse,
    DecisionHistoryEntry,
    MeetingAttendeeResponse,
    MeetingAttendeeListResponse,
    AttendeeMappingRequest,
    MeetingExportResponse,
    MeetingExportFileResponse,
    MeetingExportFileListResponse,
    MeetingRecentItem,
    MeetingRecentListResponse,
    MeetingScheduleRequest,
    UpcomingMeetingItem,
    UpcomingMeetingListResponse,
    MeetingJoinResponse,
    MeetingSegmentUpdateRequest,
    MeetingSummaryUpdateRequest,
    MeetingSegmentSplitRequest,
    MeetingSegmentSplitResponse,
    MeetingDocumentResponse,
    MeetingDocumentListResponse,
    DecisionCreateRequest,
    DecisionUpdateRequest,
    MeetingSummaryResponse,
    MeetingExportDecisionResponse,
    MeetingExportTaskResponse,
    MeetingActiveParticipantItem,
    MeetingActiveParticipantListResponse,
)


router = APIRouter(prefix="/api/workspaces/{workspace_id}/meetings", tags=["Meetings"])
decisions_router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["Decisions"])

MEETING_EXPORT_STORAGE_DIR = Path("storage/uploads/exports")
MEETING_AUDIO_STORAGE_DIR = Path("storage/uploads/audio")
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm"}


def _is_allowed_audio_file(file: UploadFile) -> bool:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in ALLOWED_AUDIO_EXTENSIONS:
        return True
    return bool(file.content_type and file.content_type.startswith("audio/"))


def _save_audio_to_local_storage(file_content: bytes, filename: str) -> tuple[str, str]:
    MEETING_AUDIO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}{Path(filename).suffix}"
    storage_path = MEETING_AUDIO_STORAGE_DIR / stored_filename
    storage_path.write_bytes(file_content)
    return str(storage_path), stored_filename


def _get_meeting_or_404(db: Session, meeting_id: uuid.UUID, workspace_id: uuid.UUID):
    meeting = meeting_crud.get_meeting(db, meeting_id)
    if not meeting or meeting.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="회의를 찾을 수 없습니다.",
        )
    return meeting


def _resolve_related_room(db: Session, workspace_id: uuid.UUID, related_room_id):
    if not related_room_id:
        return None
    room = room_crud.get_room_by_id(db, related_room_id, workspace_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="연결하려는 채팅방을 찾을 수 없습니다.",
        )
    return room

def _resolve_category(db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID | None):
    if category_id is None:
        category = room_crud.get_default_category(db, workspace_id)
    else:
        category = room_crud.get_category(db, category_id)
        if not category or category.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="워크스페이스에 속하지 않는 카테고리입니다.",
            )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="워크스페이스의 기본 카테고리를 찾을 수 없습니다.",
        )
    return category


# 실시간 녹음 시작
@router.post("/start", response_model=MeetingStartResponse, status_code=status.HTTP_201_CREATED)
def start_meeting_api(
    workspace_id: uuid.UUID,
    request: MeetingStartRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _resolve_related_room(db, workspace_id, request.related_room_id)

    category = _resolve_category(db, workspace_id, request.category_id)

    started_at = datetime.now(timezone.utc)
    title = (request.title or "").strip()
    title_is_auto = not title
    if title_is_auto:
        title = f"{started_at.month}월 {started_at.day}일 회의"

    meeting = meeting_crud.create_meeting(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        title=title,
        title_is_auto=title_is_auto,
        location=request.location,
        topic=request.topic,
        recording_mode=request.recording_mode,
        input_type="live_recording",
        started_by=uuid.UUID(current_user_id),
        related_room_id=request.related_room_id,
        status="recording",
        started_at=started_at,
    )

    ws_ticket = create_ws_ticket(current_user_id, str(meeting.id))
    reminder_result = agenda_reminder.check_on_session_start(db, category.id)

    return MeetingStartResponse(
        **MeetingResponse.model_validate(meeting).model_dump(),
        ws_ticket=ws_ticket,
        agenda_reminder=reminder_result["popup"],
    )


# 음성 파일 업로드 (등록 후 백그라운드로 8002 STT 처리 → 회의 후처리까지 자동 진행)
@router.post("/upload", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def upload_meeting_api(
    workspace_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    title: str | None = Form(default=None, max_length=200),
    file: UploadFile = File(...),
    related_room_id: uuid.UUID | None = Form(None),
    location: str | None = Form(None),
    topic: str | None = Form(None),
    category_id: uuid.UUID | None = Form(None),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _resolve_related_room(db, workspace_id, related_room_id)

    if not file.filename or not _is_allowed_audio_file(file):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="지원하지 않는 음성 파일 형식입니다.",
        )

    category = _resolve_category(db, workspace_id, category_id)

    file_content = await file.read()
    storage_path, stored_filename = _save_audio_to_local_storage(file_content, file.filename)

    workspace_file = file_crud.create_workspace_file(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        uploaded_by=uuid.UUID(current_user_id),
        original_filename=file.filename,
        stored_filename=stored_filename,
        storage_path=storage_path,
        mime_type=file.content_type,
        extension=Path(file.filename).suffix.lstrip("."),
        file_kind="audio",
        origin_type="meeting_upload",
        file_size_bytes=len(file_content),
        sha256_hash=hashlib.sha256(file_content).hexdigest(),
        version_group_id=uuid.uuid4(),
        analysis_status="pending",
    )
    resolved_title = (title or "").strip()
    title_is_auto = not resolved_title
    if title_is_auto:
        now = datetime.now(timezone.utc)
        resolved_title = f"{now.month}월 {now.day}일 회의"

    meeting = meeting_crud.create_meeting(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        title=resolved_title,
        title_is_auto=title_is_auto,
        location=location,
        topic=topic,
        input_type="audio_upload",
        started_by=uuid.UUID(current_user_id),
        related_room_id=related_room_id,
        source_file_id=workspace_file.id,
        status="created",
    )

    background_tasks.add_task(
        process_uploaded_audio_stt,
        meeting.id, workspace_id, category.id, file_content,
    )

    return MeetingResponse.model_validate(meeting)


# 실시간 녹음 종료
@router.post("/{meeting_id}/end", response_model=MeetingResponse)
def end_meeting_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)

    if meeting.input_type != "live_recording":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="실시간 녹음 회의가 아닙니다.",
        )
    if meeting.status != "recording":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="녹음 중인 회의가 아닙니다.",
        )

    ended_at = datetime.now(timezone.utc)
    duration_ms = (
        max(0, int((ended_at - meeting.started_at).total_seconds() * 1000) - meeting.paused_duration_ms)
        if meeting.started_at else None
    )

    # recording -> processing 전이를 원자적으로 시도한다. WS 종료(_finalize_meeting_if_recording)가
    # 근접한 시점에 같은 전이를 시도할 수 있으므로, 실제로 이긴 쪽만 후처리를 예약해야 중복 실행을 막는다.
    transitioned = meeting_crud.try_transition_meeting_status(
        db, meeting_id, from_status="recording", to_status="processing",
        ended_at=ended_at, duration_ms=duration_ms,
    )
    if transitioned is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="녹음 중인 회의가 아닙니다.",
        )
    meeting = transitioned

    # 각자 PC 모드는 참가자별로 별도 파일에 녹음되므로, 후처리가 찾는 단일 파일로
    # 미리 합쳐둬야 한다 (다른 참가자 소켓이 아직 연결돼 있어도 여기까지 기록된 만큼만 합침).
    if meeting.recording_mode == "individual":
        meeting_ws_router._merge_individual_recordings(meeting_id)

    # 응답은 바로 내려주고, 요약/결정사항/할 일 생성(LLM 호출 포함)은 백그라운드에서 처리.
    background_tasks.add_task(
        meeting_service.run_meeting_postprocess_and_notify,
        meeting_id=str(meeting_id),
        workspace_id=str(workspace_id),
        category_id=str(meeting.category_id),
    )

    return MeetingResponse.model_validate(meeting)


# 회의 목록 조회
@router.get("", response_model=MeetingListResponse)
def get_meeting_list(
    workspace_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meetings = meeting_crud.list_meetings(db, workspace_id)
    return MeetingListResponse(meetings=[MeetingResponse.model_validate(m) for m in meetings])

# 최근 회의록 목록 — 대시보드용, 참석인원/모순개수/미리보기 포함
@router.get("/recent", response_model=MeetingRecentListResponse)
def get_recent_meetings_api(
    workspace_id: uuid.UUID,
    limit: int = Query(default=10, ge=1, le=50),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    meetings = meeting_crud.list_recent_meetings(db, workspace_id, limit=limit)
    total_count = meeting_crud.count_meetings(db, workspace_id)

    items = []
    for m in meetings:
        summary = meeting_crud.get_meeting_summary(db, m.id)
        attendees = meeting_crud.get_attendees(db, m.id)
        items.append(MeetingRecentItem(
            id=m.id,
            title=m.title,
            started_at=m.started_at,
            duration_ms=m.duration_ms,
            attendee_count=len(attendees),
            preview=(summary.short_summary[:80] if summary and summary.short_summary else None),
            contradiction_count=contradiction_crud.count_by_meeting(db, m.id),
        ))

    return MeetingRecentListResponse(meetings=items, total_count=total_count)

# 회의록 검색 — 제목/주제/요약 텍스트 매칭 + 회의 내용 의미 검색 결합, 날짜 필터
@router.get("/search", response_model=MeetingRecentListResponse)
def search_meetings_api(
    workspace_id: uuid.UUID,
    q: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    matched: dict[uuid.UUID, "Meeting"] = {}

    if q:
        for m in meeting_crud.search_meetings_by_text(db, workspace_id, q):
            matched[m.id] = m

        try:
            chunk_results = search_hybrid(
                query_text=q, workspace_id=str(workspace_id),
                collection_name=MEETING_COLLECTION,
            )
        except Exception as e:
            print(f"[meeting_router] 회의 의미 검색 실패: {repr(e)}")
            chunk_results = []

        for r in chunk_results:
            if r.get("score", 0.0) < 0.4:
                continue
            file_id = r.get("document_id")
            if not file_id:
                continue
            meeting = meeting_crud.get_meeting_by_source_file_id(db, uuid.UUID(file_id))
            if meeting and meeting.workspace_id == workspace_id and meeting.id not in matched:
                matched[meeting.id] = meeting
    else:
        for m in meeting_crud.list_meetings_by_date_range(db, workspace_id, date_from, date_to):
            matched[m.id] = m

    results = list(matched.values())
    if date_from:
        results = [m for m in results if m.started_at and m.started_at >= date_from]
    if date_to:
        results = [m for m in results if m.started_at and m.started_at <= date_to]
    results.sort(key=lambda m: m.started_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    items = []
    for m in results:
        summary = meeting_crud.get_meeting_summary(db, m.id)
        attendees = meeting_crud.get_attendees(db, m.id)
        items.append(MeetingRecentItem(
            id=m.id,
            title=m.title,
            started_at=m.started_at,
            duration_ms=m.duration_ms,
            attendee_count=len(attendees),
            preview=(summary.short_summary[:80] if summary and summary.short_summary else None),
            contradiction_count=contradiction_crud.count_by_meeting(db, m.id),
        ))

    return MeetingRecentListResponse(meetings=items, total_count=len(items))

# 회의 예약 — 실제 녹음은 아직 시작 안 함
@router.post("/schedule", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def schedule_meeting_api(
    workspace_id: uuid.UUID,
    request: MeetingScheduleRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    category = _resolve_category(db, workspace_id, request.category_id)

    for user_id in request.attendee_ids:
        if not workspace_crud.get_membership(db, workspace_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"워크스페이스 멤버가 아닌 사용자입니다: {user_id}",
            )

    scheduled_title = (request.title or "").strip()
    title_is_auto = not scheduled_title
    if title_is_auto:
        scheduled_title = f"{request.scheduled_at.month}월 {request.scheduled_at.day}일 회의"

    meeting = meeting_crud.create_meeting(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        title=scheduled_title,
        title_is_auto=title_is_auto,
        location=request.location,
        topic=request.topic,
        input_type="live_recording",
        started_by=uuid.UUID(current_user_id),
        status="scheduled",
        scheduled_at=request.scheduled_at,
    )

    meeting_crud.set_attendees(db, meeting.id, request.attendee_ids)

    return MeetingResponse.model_validate(meeting)


# 예정된 회의 목록
@router.get("/upcoming", response_model=UpcomingMeetingListResponse)
def get_upcoming_meetings_api(
    workspace_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meetings = meeting_crud.list_upcoming_meetings(db, workspace_id)

    items = []
    for m in meetings:
        attendee_rows = meeting_crud.get_attendees(db, m.id)
        items.append(UpcomingMeetingItem(
            id=m.id,
            title=m.title,
            topic=m.topic,
            location=m.location,
            scheduled_at=m.scheduled_at,
            attendees=[
                MeetingAttendeeResponse(user_id=a.user_id, display_name=u.display_name)
                for a, u in attendee_rows
            ],
        ))
    return UpcomingMeetingListResponse(meetings=items)

# 회의에서 AI가 추출한 할 일 중 아직 검수(승인) 안 된 제안 목록
@router.get("/{meeting_id}/suggested-tasks", response_model=TaskListResponse)
def get_meeting_suggested_tasks_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    items = meeting_crud.list_suggested_tasks_by_meeting(db, meeting_id)
    return TaskListResponse(
        tasks=[TaskResponse.model_validate(i) for i in items]
    )

# 예정된 회의를 실제 녹음으로 시작
@router.post("/{meeting_id}/begin", response_model=MeetingStartResponse)
def begin_scheduled_meeting_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)

    if meeting.status != "scheduled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="예정된 회의가 아닙니다.",
        )

    transitioned = meeting_crud.try_transition_meeting_status(
        db, meeting_id, from_status="scheduled", to_status="recording",
        started_at=datetime.now(timezone.utc),
    )
    if transitioned is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="예정된 회의가 아닙니다.",
        )

    ws_ticket = create_ws_ticket(current_user_id, str(meeting_id))
    reminder_result = agenda_reminder.check_on_session_start(db, transitioned.category_id)

    return MeetingStartResponse(
        **MeetingResponse.model_validate(transitioned).model_dump(),
        ws_ticket=ws_ticket,
        agenda_reminder=reminder_result["popup"],
    )

# 회의 단건 조회
@router.get("/{meeting_id}", response_model=MeetingResponse)
def get_meeting_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)
    return MeetingResponse.model_validate(meeting)

# 회의 제목 변경
@router.patch("/{meeting_id}", response_model=MeetingResponse)
def update_meeting_title_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    request: MeetingTitleUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)
    
    updated = meeting_crud.update_meeting_info(
        db, meeting_id,
        title=request.title, location=request.location, topic=request.topic,
        title_is_auto=False,
    )
    return MeetingResponse.model_validate(updated)


# 회의 삭제
@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)
    meeting_crud.delete_meeting(db, meeting_id)


# 발화 세그먼트 목록 조회
@router.get("/{meeting_id}/segments", response_model=MeetingSegmentListResponse)
def get_meeting_segments_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    segments = meeting_crud.get_segments(db, meeting_id)
    return MeetingSegmentListResponse(
        segments=[MeetingSegmentResponse.model_validate(s) for s in segments]
    )

# 회의 원본 음성 듣기/다운로드 (실시간 녹음은 raw PCM이라 WAV 헤더를 씌워서 반환)
@router.get("/{meeting_id}/audio")
def get_meeting_audio_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)

    if not meeting.source_file_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="원본 음성 파일이 아직 없습니다.",
        )

    workspace_file = file_crud.get_file(db, meeting.source_file_id)
    if not workspace_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="원본 음성 파일을 찾을 수 없습니다.",
        )

    file_path = Path(workspace_file.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="원본 음성 파일이 존재하지 않습니다.",
        )

    if workspace_file.mime_type == "audio/L16":
        # 실시간 녹음 - raw PCM16LE 16kHz mono라 브라우저가 바로 못 읽음. WAV 헤더를 씌워서 반환.
        pcm_bytes = file_path.read_bytes()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(pcm_bytes)
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="audio/wav")

    return FileResponse(
        path=file_path,
        media_type=workspace_file.mime_type or "application/octet-stream",
        filename=workspace_file.original_filename,
    )

# 발화 세그먼트 내용 수정
@router.patch("/{meeting_id}/segments/{segment_id}", response_model=MeetingSegmentResponse)
def update_meeting_segment_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    segment_id: uuid.UUID,
    request: MeetingSegmentUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    if request.content is None and request.speaker_label is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 내용이 없습니다.",
        )
    
    segment = meeting_crud.get_segment(db, segment_id)
    if not segment or segment.meeting_id != meeting_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="발화 세그먼트를 찾을 수 없습니다.",
        )

    updated = meeting_crud.update_segment_content(
        db, segment_id, content=request.content, speaker_label=request.speaker_label,
    )    
    return MeetingSegmentResponse.model_validate(updated)

# 발화 세그먼트 분할 (한 세그먼트에 두 사람 발언이 섞였을 때)
@router.post("/{meeting_id}/segments/{segment_id}/split", response_model=MeetingSegmentSplitResponse)
def split_meeting_segment_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    segment_id: uuid.UUID,
    request: MeetingSegmentSplitRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    segment = meeting_crud.get_segment(db, segment_id)
    if not segment or segment.meeting_id != meeting_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="발화 세그먼트를 찾을 수 없습니다.",
        )
    if segment.end_ms - segment.start_ms < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="구간이 너무 짧아 분할할 수 없습니다.",
        )

    result = meeting_crud.split_segment(
        db, segment_id,
        first_content=request.first_content,
        second_content=request.second_content,
        first_speaker_label=request.first_speaker_label,
        second_speaker_label=request.second_speaker_label,
    )
    first, second = result
    return MeetingSegmentSplitResponse(
        first=MeetingSegmentResponse.model_validate(first),
        second=MeetingSegmentResponse.model_validate(second),
    )

# 회의 요약 조회
@router.get("/{meeting_id}/summary", response_model=MeetingSummaryResponse)
def get_meeting_summary_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    summary = meeting_crud.get_meeting_summary(db, meeting_id)
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="회의 요약을 찾을 수 없습니다.",
        )
    return MeetingSummaryResponse.model_validate(summary)

# 회의 요약 수정
@router.patch("/{meeting_id}/summary", response_model=MeetingSummaryResponse)
def update_meeting_summary_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    request: MeetingSummaryUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    existing = meeting_crud.get_meeting_summary(db, meeting_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="회의 요약을 찾을 수 없습니다.",
        )

    if request.short_summary is None and request.full_summary is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 내용이 없습니다.",
        )

    update_fields = {}
    if request.short_summary is not None:
        update_fields["short_summary"] = request.short_summary
    if request.full_summary is not None:
        update_fields["full_summary"] = request.full_summary

    updated = meeting_crud.upsert_summary(db, meeting_id, **update_fields)
    return MeetingSummaryResponse.model_validate(updated)

# 회의록 내보내기용 데이터 일괄 조회 — 문서 조립은 프론트에서 처리
@router.get("/{meeting_id}/export", response_model=MeetingExportResponse)
def get_meeting_export_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)

    summary = meeting_crud.get_meeting_summary(db, meeting_id)
    attendee_rows = meeting_crud.get_attendees(db, meeting_id)
    segments = meeting_crud.get_segments(db, meeting_id)
    decisions = meeting_crud.list_decisions_by_meeting(db, meeting_id)
    tasks = meeting_crud.list_suggested_tasks_by_meeting(db, meeting_id)

    return MeetingExportResponse(
        meeting_id=meeting.id,
        title=meeting.title,
        location=meeting.location,
        topic=meeting.topic,
        started_at=meeting.started_at,
        attendees=[
            MeetingAttendeeResponse(user_id=attendee.user_id, display_name=user.display_name)
            for attendee, user in attendee_rows
        ],
        meeting_purpose=summary.meeting_purpose if summary else None,
        full_summary=summary.full_summary if summary else None,
        short_summary=summary.short_summary if summary else None,
        discussion_points=summary.discussion_points if summary else None,
        next_steps=summary.next_steps if summary else None,
        decisions=[
            MeetingExportDecisionResponse(
                title=d.title, decision_text=d.decision_text, reason=d.reason,
            )
            for d in decisions
        ],
        action_items=[
            MeetingExportTaskResponse(
                title=t.title, description=t.description,
                assignee_label=t.assignee_label, due_at=t.due_at,
            )
            for t in tasks
        ],
        filtered_transcript=summary.filtered_transcript if summary else None,
        segments=[MeetingSegmentResponse.model_validate(s) for s in segments],
    )

def _build_export_document_text(meeting, summary, attendee_rows, segments) -> str:
    lines = [f"# {meeting.title} 회의록"]
    if meeting.location:
        lines.append(f"장소: {meeting.location}")
    if meeting.topic:
        lines.append(f"주제: {meeting.topic}")
    attendee_names = ", ".join(user.display_name for _, user in attendee_rows)
    if attendee_names:
        lines.append(f"참석자: {attendee_names}")
    if summary and summary.meeting_purpose:
        lines.append(f"\n## 회의 목적\n{summary.meeting_purpose}")
    if summary and summary.full_summary:
        lines.append(f"\n## 전체 내용\n{summary.full_summary}")
    if summary and summary.short_summary:
        lines.append(f"\n## 요약\n{summary.short_summary}")
    if summary and summary.next_steps:
        lines.append(f"\n## 향후 계획\n{summary.next_steps}")
    if segments:
        transcript = "\n".join(f"[{s.speaker_label or '화자 미상'}] {s.content}" for s in segments)
        lines.append(f"\n## 스크립트\n{transcript}")
    return "\n".join(lines)


# 회의록 PDF 내보내기 - 완성된 PDF 파일을 서버에 저장/등록
@router.post("/{meeting_id}/export", response_model=MeetingExportFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_meeting_export_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)

    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF 파일만 업로드 가능합니다.",
        )

    file_content = await file.read()
    MEETING_EXPORT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}.pdf"
    storage_path = MEETING_EXPORT_STORAGE_DIR / stored_filename
    storage_path.write_bytes(file_content)

    workspace_file = file_crud.create_meeting_export(
        db,
        workspace_id=workspace_id,
        category_id=meeting.category_id,
        meeting_id=meeting_id,
        uploaded_by=uuid.UUID(current_user_id),
        original_filename=file.filename,
        stored_filename=stored_filename,
        storage_path=str(storage_path),
        file_size_bytes=len(file_content),
        sha256_hash=hashlib.sha256(file_content).hexdigest(),
    )

    # 검색/모순 감지 대상에 포함되도록 임베딩 — 부가 기능이라 실패해도 파일 저장 자체는 성공 처리
    try:
        summary = meeting_crud.get_meeting_summary(db, meeting_id)
        attendee_rows = meeting_crud.get_attendees(db, meeting_id)
        segments = meeting_crud.get_segments(db, meeting_id)
        document_text = _build_export_document_text(meeting, summary, attendee_rows, segments)
        load_result = load_document(db, workspace_file.id, chunks=[
            {"style": "body", "content": document_text, "page_number": 1}
        ])
        if load_result.get("status") != "success":
            print(f"[meeting_router] 회의록 내보내기 임베딩 실패: {load_result}")
    except Exception as e:
        print(f"[meeting_router] 회의록 내보내기 임베딩 중 예외: {repr(e)}")

    return MeetingExportFileResponse(
        export_id=workspace_file.id,
        meeting_id=meeting_id,
        meeting_title=meeting.title,
        filename=workspace_file.original_filename,
        created_at=workspace_file.created_at,
    )


# 워크스페이스 전체 회의록 내보내기 이력
@decisions_router.get("/meeting-exports", response_model=MeetingExportFileListResponse)
def list_meeting_exports_api(
    workspace_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    rows = file_crud.list_meeting_exports(db, workspace_id)
    return MeetingExportFileListResponse(
        exports=[
            MeetingExportFileResponse(
                export_id=wf.id, meeting_id=wf.related_meeting_id,
                meeting_title=title, filename=wf.original_filename,
                created_at=wf.created_at,
            )
            for wf, title in rows
        ]
    )


# 회의 결정사항 목록 조회
@router.get("/{meeting_id}/decisions", response_model=DecisionListResponse)
def get_meeting_decisions_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    decisions = meeting_crud.list_decisions_by_meeting(db, meeting_id)
    return DecisionListResponse(
        decisions=[DecisionResponse.model_validate(d) for d in decisions]
    )

# 결정사항 생성 (회의록 탭에서 수동 추가)
@router.post("/{meeting_id}/decisions", response_model=DecisionResponse, status_code=status.HTTP_201_CREATED)
def create_meeting_decision_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    request: DecisionCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    decision = meeting_crud.create_decision(
        db,
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        title=request.title,
        decision_text=request.decision_text,
        reason=request.reason,
        status=request.status,
        decided_at=request.decided_at or datetime.now(timezone.utc),
    )
    return DecisionResponse.model_validate(decision)


# 결정사항 수정
@router.patch("/{meeting_id}/decisions/{decision_id}", response_model=DecisionResponse)
def update_meeting_decision_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    decision_id: uuid.UUID,
    request: DecisionUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    decision = meeting_crud.get_decision(db, decision_id)
    if not decision or decision.meeting_id != meeting_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="결정사항을 찾을 수 없습니다.",
        )

    update_fields = request.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 내용이 없습니다.",
        )

    updated = meeting_crud.update_decision(db, decision_id, **update_fields)
    return DecisionResponse.model_validate(updated)


# 결정사항 삭제
@router.delete("/{meeting_id}/decisions/{decision_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting_decision_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    decision_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    decision = meeting_crud.get_decision(db, decision_id)
    if not decision or decision.meeting_id != meeting_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="결정사항을 찾을 수 없습니다.",
        )

    meeting_crud.delete_decision(db, decision_id)

# 실시간 녹음 일시정지
@router.post("/{meeting_id}/pause", response_model=MeetingResponse)
def pause_meeting_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)

    if meeting.input_type != "live_recording":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="실시간 녹음 회의가 아닙니다.",
        )

    transitioned = meeting_crud.try_transition_meeting_status(
        db, meeting_id, from_status="recording", to_status="paused",
        paused_at=datetime.now(timezone.utc),
    )
    if transitioned is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="녹음 중인 회의가 아닙니다.",
        )

    meeting_ws_router.set_stream_paused(meeting_id, True)
    return MeetingResponse.model_validate(transitioned)


# 실시간 녹음 재개
@router.post("/{meeting_id}/resume", response_model=MeetingResponse)
def resume_meeting_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)

    if meeting.input_type != "live_recording":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="실시간 녹음 회의가 아닙니다.",
        )
    if meeting.status != "paused" or meeting.paused_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="일시정지 상태가 아닙니다.",
        )

    additional_pause_ms = int(
        (datetime.now(timezone.utc) - meeting.paused_at).total_seconds() * 1000
    )

    transitioned = meeting_crud.try_transition_meeting_status(
        db, meeting_id, from_status="paused", to_status="recording",
        paused_duration_ms=meeting.paused_duration_ms + additional_pause_ms,
        paused_at=None,
    )
    if transitioned is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="일시정지 상태가 아닙니다.",
        )

    meeting_ws_router.set_stream_paused(meeting_id, False)
    return MeetingResponse.model_validate(transitioned)

# 화자 라벨(SPEAKER_00 등)을 실명으로 매핑 — 회의 진행 중/종료 후 언제든 호출 가능
@router.patch("/{meeting_id}/speakers")
def update_meeting_speakers_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    request: SpeakerLabelMappingRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    updated = meeting_crud.update_speaker_labels(db, meeting_id, request.mapping)
    return {
        "status": "success",
        "meeting_id": str(meeting_id),
        "speaker_labels": updated.speaker_labels,
        "message": "화자 이름이 매핑되었습니다.",
    }

# 진행 중인 회의에 참가 — individual 모드는 본인 마이크로, 그 외엔 보기 전용으로 ws_ticket 발급
@router.post("/{meeting_id}/join", response_model=MeetingJoinResponse)
def join_meeting_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    meeting = _get_meeting_or_404(db, meeting_id, workspace_id)

    if meeting.status != "recording":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="녹음 중인 회의가 아닙니다.",
        )

    # individual(각자 PC) 모드는 기존처럼 각자 마이크로 참가. 그 외(single_device,
    # 한 대의 PC) 모드는 오디오는 이미 호스트 연결이 담당하므로 보기 전용으로만 참가시킨다.
    view_only = meeting.recording_mode != "individual"
    ws_ticket = create_ws_ticket(current_user_id, str(meeting_id), view_only=view_only)
    return MeetingJoinResponse(ws_ticket=ws_ticket)

# 참석 인원 조회
@router.get("/{meeting_id}/attendees", response_model=MeetingAttendeeListResponse)
def get_meeting_attendees_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    rows = meeting_crud.get_attendees(db, meeting_id)
    return MeetingAttendeeListResponse(
        attendees=[
            MeetingAttendeeResponse(user_id=attendee.user_id, display_name=user.display_name)
            for attendee, user in rows
        ]
    )

# 지금 이 회의에 실시간으로 접속해 있는 사람 목록 (녹음 연결 + 뷰어 연결)
@router.get("/{meeting_id}/active-participants", response_model=MeetingActiveParticipantListResponse)
def get_meeting_active_participants_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    user_ids = meeting_ws_router.get_active_participant_ids(meeting_id)
    participants = []
    for user_id in user_ids:
        user = auth_crud.get_user_by_id(db, user_id)
        if user:
            participants.append(
                MeetingActiveParticipantItem(
                    user_id=user.id,
                    display_name=user.display_name,
                    profile_image_url=user.profile_image_url,
                )
            )
    return MeetingActiveParticipantListResponse(participants=participants)


# 참석 인원 지정/수정 — 워크스페이스 멤버 중에서만 선택 가능
@router.patch("/{meeting_id}/attendees", response_model=MeetingAttendeeListResponse)
def update_meeting_attendees_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    request: AttendeeMappingRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    for user_id in request.user_ids:
        if not workspace_crud.get_membership(db, workspace_id, user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"워크스페이스 멤버가 아닌 사용자입니다: {user_id}",
            )

    rows = meeting_crud.set_attendees(db, meeting_id, request.user_ids)
    return MeetingAttendeeListResponse(
        attendees=[
            MeetingAttendeeResponse(user_id=attendee.user_id, display_name=user.display_name, is_initial=attendee.is_initial)
            for attendee, user in rows
        ]
    )

# 워크스페이스 전체 결정사항 조회 (기본: status=active, 변경 이력 포함)
@decisions_router.get("/decisions", response_model=DecisionWithHistoryListResponse)
def get_workspace_decisions_api(
    workspace_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    decisions = meeting_crud.list_decisions_by_workspace(db, workspace_id, status=status_filter)

    results = []
    for d in decisions:
        chain = meeting_crud.get_decision_history_chain(db, d.id)
        history = [
            DecisionHistoryEntry(value=c.decision_text, reason=c.reason, decided_at=c.decided_at, status=c.status)
            for c in chain
        ]
        item = DecisionWithHistoryResponse.model_validate(d)
        item.history = history
        results.append(item)

    return DecisionWithHistoryListResponse(decisions=results)

# 회의에 첨부된 참고 문서 목록 조회
@router.get("/{meeting_id}/documents", response_model=MeetingDocumentListResponse)
def get_meeting_documents_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    files = file_crud.list_files_by_meeting(db, meeting_id)
    return MeetingDocumentListResponse(
        documents=[MeetingDocumentResponse.model_validate(f) for f in files]
    )

# 회의 첨부 문서 삭제(연결 해제)
@router.delete("/{meeting_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting_document_api(
    workspace_id: uuid.UUID,
    meeting_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_meeting_or_404(db, meeting_id, workspace_id)

    try:
        result = document_service.unlink_or_delete_meeting_document(db, document_id, meeting_id)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="회의에 첨부된 문서를 찾을 수 없습니다.",
        )

    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"문서 삭제 중 오류가 발생했습니다: {result.get('error')}",
        )