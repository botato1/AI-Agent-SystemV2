import json
import os
from fastapi import APIRouter, HTTPException

from ..core.config import MEETINGS_DIR

router = APIRouter()

# 목록 응답에 포함할 메타 필드 (segments 전체는 상세 조회에서만)
_SUMMARY_FIELDS = (
    "meeting_id", "session_id", "started_at", "ended_at",
    "status", "speaker_mode", "refined",
)


@router.get("/meetings")
async def list_meetings():
    """저장된 회의 목록 조회 (최신순). 회의록 아카이브(D-3) UI가 그대로 사용 가능."""
    items = []
    for meeting_id in sorted(os.listdir(MEETINGS_DIR), reverse=True):
        path = os.path.join(MEETINGS_DIR, meeting_id, "transcript.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue  # 저장 도중 깨진 파일은 목록에서 제외
        summary = {k: meta.get(k) for k in _SUMMARY_FIELDS}
        summary["segment_count"] = len(meta.get("segments", []))
        items.append(summary)
    return {"count": len(items), "meetings": items}


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str):
    """회의 하나의 전체 회의록(세그먼트 포함) 조회."""
    # 경로 조작(path traversal) 방지
    if "/" in meeting_id or "\\" in meeting_id or ".." in meeting_id:
        raise HTTPException(status_code=400, detail="잘못된 meeting_id")

    path = os.path.join(MEETINGS_DIR, meeting_id, "transcript.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="해당 회의록을 찾을 수 없습니다.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
