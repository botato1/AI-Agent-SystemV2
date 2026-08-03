# backend/schemas/meeting_schema.py

"""
음성 회의, 회의 발언 세그먼트, 회의 요약, 결정사항과 관련된
Pydantic 스키마를 정의한다.

카테고리 범위 설계:
- meetings.category_id는 회의가 속한 카테고리를 나타낸다.
- MVP에서는 워크스페이스의 기본 카테고리를 서비스 계층에서 자동 적용한다.
- 향후 여러 카테고리를 지원할 때는 회의 시작 단계에서 현재 화면의
  카테고리를 적용하거나 사용자가 대상 카테고리를 선택하도록 한다.
- related_room_id가 있으면 연결된 rooms.category_id를 사용한다.
- 회의 원본 음성 파일은 meetings.category_id를
  workspace_files.category_id로 상속받는다.

related_room_id는 선택값이며, 모순 감지 범위는 meetings.category_id를
기준으로 결정한다.

결정사항은 meeting_id를 통해 회의와 카테고리를 확인할 수 있으므로
category_id를 별도로 저장하지 않는다.

채팅 메시지에서는 결정사항을 추출하지 않는다.

TODO:
- 회의, 발언 세그먼트, 요약, 결정사항 조회 API의 요청·응답 스키마는
  관련 라우터 구현 시 별도로 정의
- 외부 STT 서버 요청·응답 형식은 stt_schema.py에서 별도로 관리
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.schemas.common_schema import (
    SoftDeleteSchema,
    TimestampSchema,
)
from backend.schemas.type_schema import (
    DecisionStatus,
    GenerationStatus,
    MeetingInputType,
    MeetingStatus,
)


# =============================================================================
# Re:Call: meetings
# =============================================================================

class MeetingSchema(TimestampSchema, SoftDeleteSchema):
    """
    실시간 녹음 또는 음성 파일 업로드로 생성된 회의를 표현한다.

    서비스 계층에서 다음 관계를 검증해야 한다.

        meetings.workspace_id == categories.workspace_id

    related_room_id가 있는 경우:

        meetings.workspace_id == rooms.workspace_id
        meetings.category_id == rooms.category_id

    source_file_id가 있는 경우:

        meetings.workspace_id == workspace_files.workspace_id
        meetings.category_id == workspace_files.category_id
        workspace_files.file_kind == "audio"
    """

    id: UUID
    workspace_id: UUID
    category_id: UUID

    related_room_id: Optional[UUID] = None
    source_file_id: Optional[UUID] = None

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )
    title_is_auto: bool = False
    location: Optional[str] = Field(default=None, max_length=200)
    topic: Optional[str] = Field(default=None, max_length=200)
    input_type: MeetingInputType
    status: MeetingStatus

    started_by: UUID
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    duration_ms: Optional[int] = Field(
        default=None,
        ge=0,
    )

    @model_validator(mode="after")
    def _validate_meeting_time(self) -> "MeetingSchema":
        if (
            self.started_at is not None
            and self.ended_at is not None
            and self.ended_at < self.started_at
        ):
            raise ValueError(
                "ended_at은 started_at보다 빠를 수 없습니다."
            )

        return self


# =============================================================================
# Re:Call: meeting_segments
# =============================================================================

class MeetingSegmentSchema(TimestampSchema):
    """
    STT 처리로 생성된 회의 발언 세그먼트 하나를 표현한다.

    DB 제약조건:

        UNIQUE(meeting_id, segment_index)
        end_ms > start_ms
    """

    id: UUID
    meeting_id: UUID

    speaker_label: Optional[str] = Field(
        default=None,
        max_length=50,
    )
    speaker_user_id: Optional[UUID] = None

    content: str = Field(
        ...,
        min_length=1,
    )

    start_ms: int = Field(
        ...,
        ge=0,
    )
    end_ms: int = Field(
        ...,
        ge=0,
    )
    segment_index: int = Field(
        ...,
        ge=0,
    )

    stt_confidence: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )
    language_code: Optional[str] = Field(
        default=None,
        max_length=20,
    )

    is_edited: bool

    @model_validator(mode="after")
    def _validate_segment_time(self) -> "MeetingSegmentSchema":
        if self.end_ms <= self.start_ms:
            raise ValueError(
                "end_ms는 start_ms보다 커야 합니다."
            )

        return self


# =============================================================================
# Re:Call: meeting_summaries
# =============================================================================

class MeetingSummarySchema(TimestampSchema):
    """
    회의 종료 후 생성되는 회의 요약을 표현한다.

    meeting_id는 meetings.id를 참조하며,
    회의당 요약 하나만 존재하도록 DB에서 UNIQUE 제약을 적용한다.
    """

    id: UUID
    meeting_id: UUID

    full_summary: Optional[str] = None
    short_summary: Optional[str] = None
    filtered_transcript: Optional[str] = None
    discussion_points: Optional[Any] = None
    full_transcript: Optional[str] = None

    generation_status: GenerationStatus
    generation_error: Optional[str] = None

    model_name: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    generated_at: Optional[datetime] = None


# =============================================================================
# Re:Call: decisions
# =============================================================================

class DecisionSchema(TimestampSchema, SoftDeleteSchema):
    """
    회의 종료 후 추출된 결정사항 하나를 표현한다.

    결정사항은 반드시 하나의 회의에 속한다.
    source_segment_id가 있으면 해당 세그먼트가 meeting_id의 회의에
    속하는지 서비스 계층에서 검증한다.

    supersedes_decision_id가 있으면 이전 결정과 현재 결정의
    workspace_id 및 category_id가 동일한지 검증한다.
    category_id는 각 결정의 meeting_id를 통해 확인한다.
    """

    id: UUID
    workspace_id: UUID
    meeting_id: UUID
    source_segment_id: Optional[UUID] = None

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
    )
    decision_text: str = Field(
        ...,
        min_length=1,
    )
    reason: Optional[str] = None

    status: DecisionStatus
    supersedes_decision_id: Optional[UUID] = None

    confidence_score: Optional[Decimal] = Field(
        default=None,
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=4,
    )

    decided_at: datetime

# =============================================================================
# Re:Call: meetings API 요청/응답
# =============================================================================

class MeetingStartRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    related_room_id: Optional[UUID] = None
    location: Optional[str] = Field(default=None, max_length=200)
    topic: Optional[str] = Field(default=None, max_length=200)
    recording_mode: Literal["single_device", "individual"] = "single_device"


class MeetingResponse(TimestampSchema):
    id: UUID
    workspace_id: UUID
    category_id: UUID
    related_room_id: Optional[UUID] = None
    source_file_id: Optional[UUID] = None

    title: str
    title_is_auto: bool = False
    location: Optional[str] = None
    topic: Optional[str] = None
    recording_mode: str = "single_device"
    input_type: MeetingInputType
    status: MeetingStatus

    started_by: UUID
    started_at: Optional[datetime] = None
    scheduled_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class MeetingStartResponse(MeetingResponse):
    ws_ticket: str

class AgendaReminderItem(BaseModel):
    id: UUID
    title: str
    decision_text: str
    reason: Optional[str] = None


class AgendaReminderPopup(BaseModel):
    type: str
    message: str
    items: list[AgendaReminderItem] = Field(default_factory=list)


class MeetingStartResponse(MeetingResponse):
    ws_ticket: str
    agenda_reminder: AgendaReminderPopup

class MeetingListResponse(BaseModel):
    meetings: list[MeetingResponse] = Field(default_factory=list)


class MeetingSegmentResponse(TimestampSchema):
    id: UUID
    meeting_id: UUID
    speaker_label: Optional[str] = None
    speaker_user_id: Optional[UUID] = None
    content: str
    start_ms: int
    end_ms: int
    segment_index: int
    stt_confidence: Optional[Decimal] = None
    is_edited: bool


class MeetingSegmentListResponse(BaseModel):
    segments: list[MeetingSegmentResponse] = Field(default_factory=list)


class MeetingSummaryResponse(TimestampSchema):
    id: UUID
    meeting_id: UUID
    full_summary: Optional[str] = None
    short_summary: Optional[str] = None
    filtered_transcript: Optional[str] = None
    discussion_points: Optional[Any] = None
    generation_status: GenerationStatus
    generated_at: Optional[datetime] = None

class DecisionResponse(TimestampSchema):
    id: UUID
    workspace_id: UUID
    meeting_id: UUID
    title: str
    decision_text: str
    reason: Optional[str] = None
    status: DecisionStatus
    decided_at: datetime


class DecisionListResponse(BaseModel):
    decisions: list[DecisionResponse] = Field(default_factory=list)

class DecisionHistoryEntry(BaseModel):
    value: str
    reason: Optional[str] = None
    decided_at: datetime
    status: DecisionStatus


class DecisionWithHistoryResponse(TimestampSchema):
    id: UUID
    workspace_id: UUID
    meeting_id: UUID
    title: str
    decision_text: str
    reason: Optional[str] = None
    status: DecisionStatus
    decided_at: datetime
    history: list[DecisionHistoryEntry] = Field(default_factory=list)


class DecisionWithHistoryListResponse(BaseModel):
    decisions: list[DecisionWithHistoryResponse] = Field(default_factory=list)

class SpeakerLabelMappingRequest(BaseModel):
    mapping: dict[str, str] = Field(
        ...,
        description="원본 화자 라벨(예: SPEAKER_00) → 실명 매핑",
    )

class MeetingTitleUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)
    topic: Optional[str] = Field(default=None, max_length=200)

class MeetingAttendeeResponse(BaseModel):
    user_id: UUID
    display_name: Optional[str] = None


class MeetingAttendeeListResponse(BaseModel):
    attendees: list[MeetingAttendeeResponse] = Field(default_factory=list)


class AttendeeMappingRequest(BaseModel):
    user_ids: list[UUID] = Field(default_factory=list)

class MeetingExportResponse(BaseModel):
    meeting_id: UUID
    title: str
    topic: Optional[str] = None
    location: Optional[str] = None
    started_at: Optional[datetime] = None
    attendees: list[MeetingAttendeeResponse] = Field(default_factory=list)
    short_summary: Optional[str] = None
    filtered_transcript: Optional[str] = None
    segments: list[MeetingSegmentResponse] = Field(default_factory=list)

class MeetingRecentItem(BaseModel):
    id: UUID
    title: str
    started_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    attendee_count: int
    preview: Optional[str] = None
    contradiction_count: int


class MeetingRecentListResponse(BaseModel):
    meetings: list[MeetingRecentItem] = Field(default_factory=list)
    total_count: int

class MeetingScheduleRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    topic: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=200)
    scheduled_at: datetime
    attendee_ids: list[UUID] = Field(default_factory=list)


class UpcomingMeetingItem(BaseModel):
    id: UUID
    title: str
    topic: Optional[str] = None
    location: Optional[str] = None
    scheduled_at: datetime
    attendees: list[MeetingAttendeeResponse] = Field(default_factory=list)


class UpcomingMeetingListResponse(BaseModel):
    meetings: list[UpcomingMeetingItem] = Field(default_factory=list)

class MeetingJoinResponse(BaseModel):
    ws_ticket: str

class MeetingSegmentUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class MeetingSummaryUpdateRequest(BaseModel):
    short_summary: str
