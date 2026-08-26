# backend/schemas/dashboard_schema.py

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DashboardSummaryResponse(BaseModel):
    total_meeting_count: int
    member_count: int
    last_meeting_at: Optional[datetime] = None
    week_meeting_count: int
    week_duration_ms: int
    week_contradiction_count: int