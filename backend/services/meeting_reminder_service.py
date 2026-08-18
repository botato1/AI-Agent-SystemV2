# backend/services/meeting_reminder_service.py

"""예약된 회의 임박 알림 — 내 파트

기존 스케줄러 인프라가 없어 asyncio 백그라운드 루프로 구현. 회의 시작
reminder_minutes분 전 시점에 도달하면 참석자 전원에게 알림을 1회만 보낸다
(같은 회의에 동일 타입 알림이 이미 있으면 스킵 - notification_crud.reminder_
already_sent로 판단).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.db.crud import meeting_crud, notification_crud
from backend.db.session import SessionLocal

REMINDER_MINUTES_BEFORE = 10
KST = ZoneInfo("Asia/Seoul")


def _format_meeting_time_kr(dt: datetime) -> str:
    local = dt.astimezone(KST)
    period = "오전" if local.hour < 12 else "오후"
    hour12 = local.hour % 12 or 12
    return f"{period} {hour12}:{local.minute:02d}"


def check_and_send_meeting_reminders(reminder_minutes: int = REMINDER_MINUTES_BEFORE) -> None:
    db = SessionLocal()
    try:
        meetings = meeting_crud.list_meetings_needing_reminder(db, reminder_minutes)
        for meeting in meetings:
            if notification_crud.reminder_already_sent(db, "meeting", meeting.id, "meeting_reminder"):
                continue

            time_text = _format_meeting_time_kr(meeting.scheduled_at)
            message = f"'{meeting.title}' 회의가 {reminder_minutes}분 후 시작됩니다 ({time_text})"

            attendees = meeting_crud.get_attendees(db, meeting.id)
            for attendee, _user in attendees:
                if not notification_crud.is_notification_enabled(
                    db, meeting.workspace_id, attendee.user_id, "meeting_reminder",
                ):
                    continue
                notification_crud.create_notification(
                    db,
                    user_id=attendee.user_id,
                    workspace_id=meeting.workspace_id,
                    type="meeting_reminder",
                    title="회의 임박 알림",
                    message=message,
                    ref_type="meeting",
                    ref_id=meeting.id,
                )
    except Exception as e:
        print(f"[meeting_reminder_service] 알림 확인 중 오류: {repr(e)}")
    finally:
        db.close()