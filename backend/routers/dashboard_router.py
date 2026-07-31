# backend/routers/dashboard_router.py

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import contradiction_crud, meeting_crud, workspace_crud
from backend.schemas.dashboard_schema import DashboardSummaryResponse

router = APIRouter(prefix="/api/workspaces/{workspace_id}/dashboard", tags=["Dashboard"])


def _week_range(now: datetime) -> tuple[datetime, datetime]:
    """이번 주 월요일 00:00(UTC) ~ 다음 주 월요일 00:00(UTC)."""
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return week_start, week_start + timedelta(days=7)


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary_api(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    week_start, week_end = _week_range(datetime.now(timezone.utc))

    total_meeting_count = meeting_crud.count_meetings(db, workspace_id)
    member_count = len(workspace_crud.list_members(db, workspace_id))
    last_meeting_at = meeting_crud.get_last_meeting_at(db, workspace_id)
    week_stats = meeting_crud.get_week_meeting_stats(db, workspace_id, week_start, week_end)
    week_contradiction_count = contradiction_crud.count_in_range(db, workspace_id, week_start, week_end)

    return DashboardSummaryResponse(
        total_meeting_count=total_meeting_count,
        member_count=member_count,
        last_meeting_at=last_meeting_at,
        week_meeting_count=week_stats["count"],
        week_duration_ms=week_stats["duration_ms"],
        week_contradiction_count=week_contradiction_count,
    )