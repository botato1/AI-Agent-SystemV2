# backend/routers/meeting_router.py

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.security import create_ws_ticket
from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import meeting_crud, room_crud, file_crud
from backend.graphs.meeting_postprocess_graph import run_meeting_postprocess
from backend.schemas.meeting_schema import (
    MeetingStartRequest,
    MeetingResponse,
    MeetingListResponse,
    MeetingSegmentListResponse,
    MeetingSegmentResponse,
    MeetingSummaryResponse,
    DecisionListResponse,
    DecisionResponse,
    MeetingStartResponse,
)


router = APIRouter(prefix="/api/workspaces/{workspace_id}/meetings", tags=["Meetings"])

# TODO: NAS 연결되면 이 경로/저장 로직을 NAS 저장으로 교체 (document_service.py와 동일한 임시 조치)
MEETING_AUDIO_STORAGE_DIR = Path("data/uploads/audio")
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

    category = room_crud.get_default_category(db, workspace_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="워크스페이스의 기본 카테고리를 찾을 수 없습니다.",
        )

    meeting = meeting_crud.create_meeting(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        title=request.title,
        input_type="live_recording",
        started_by=uuid.UUID(current_user_id),
        related_room_id=request.related_room_id,
        status="recording",
        started_at=datetime.now(timezone.utc),
    )

    ws_ticket = create_ws_ticket(current_user_id, str(meeting.id))

    return MeetingStartResponse(
        **MeetingResponse.model_validate(meeting).model_dump(),
        ws_ticket=ws_ticket,
    )


# 음성 파일 업로드 (등록만 — 실제 STT 연동은 후속 작업에서 처리)
@router.post("/upload", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def upload_meeting_api(
    workspace_id: uuid.UUID,
    title: str = Form(..., min_length=1, max_length=200),
    file: UploadFile = File(...),
    related_room_id: uuid.UUID | None = Form(None),
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

    category = room_crud.get_default_category(db, workspace_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="워크스페이스의 기본 카테고리를 찾을 수 없습니다.",
        )

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
        version_group_id=uuid.uuid4(),
        analysis_status="pending",
    )

    meeting = meeting_crud.create_meeting(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        title=title,
        input_type="audio_upload",
        started_by=uuid.UUID(current_user_id),
        related_room_id=related_room_id,
        source_file_id=workspace_file.id,
        status="created",
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
        int((ended_at - meeting.started_at).total_seconds() * 1000)
        if meeting.started_at else None
    )

    meeting = meeting_crud.update_meeting_status(
        db, meeting_id, status="processing", ended_at=ended_at, duration_ms=duration_ms,
    )

    # 응답은 바로 내려주고, 요약/결정사항/할 일 생성(LLM 호출 포함)은 백그라운드에서 처리.
    # meeting_postprocess_node 자체가 status='processing'이 아니면 거부하므로,
    # WS 종료 트리거와 겹쳐도 한쪽만 실제로 실행된다.
    background_tasks.add_task(
        run_meeting_postprocess,
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