import json
import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..core.config import MEETINGS_DIR
from ..services.refine_service import refine_meeting

router = APIRouter()


class SegmentEditRequest(BaseModel):
    text: str

# 목록 응답에 포함할 메타 필드 (segments 전체는 상세 조회에서만)
_SUMMARY_FIELDS = (
    "meeting_id", "session_id", "started_at", "ended_at",
    "status", "speaker_mode", "refined",
)


@router.get("/meetings")
async def list_meetings():
    """저장된 회의 목록 조회 (최신순). 회의록 아카이브(D-3) UI가 그대로 사용 가능."""
    items = []
    for meeting_id in os.listdir(MEETINGS_DIR):
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

    # meeting_id는 "세션ID_시각" 형태라 문자열 정렬하면 세션ID 알파벳순이 먼저 적용됨
    # → 실제 시작 시각 기준으로 정렬해야 진짜 최신순이 됨
    items.sort(key=lambda m: m.get("started_at") or "", reverse=True)
    return {"count": len(items), "meetings": items}


def _validate_meeting_id(meeting_id: str) -> None:
    """경로 조작(path traversal) 방지."""
    if "/" in meeting_id or "\\" in meeting_id or ".." in meeting_id:
        raise HTTPException(status_code=400, detail="잘못된 meeting_id")


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str):
    """회의 하나의 전체 회의록(세그먼트 포함) 조회."""
    _validate_meeting_id(meeting_id)
    path = os.path.join(MEETINGS_DIR, meeting_id, "transcript.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="해당 회의록을 찾을 수 없습니다.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@router.patch("/meetings/{meeting_id}/segments/{index}")
async def edit_segment(meeting_id: str, index: int, body: SegmentEditRequest):
    """
    회의록 세그먼트 텍스트 수동 수정 (D-3 회의록 수정 UI용).
    STT가 잘못 인식한 텍스트를 사용자가 직접 고칠 수 있게 함.
    수정된 세그먼트는 user_edited=True로 표시되어, 이후 재분석(refine)이
    실행되더라도 이 값을 존중하고 덮어쓰지 않아야 함(호출부 책임).
    """
    _validate_meeting_id(meeting_id)
    path = os.path.join(MEETINGS_DIR, meeting_id, "transcript.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="해당 회의록을 찾을 수 없습니다.")

    with open(path, encoding="utf-8") as f:
        meta = json.load(f)

    segments = meta.get("segments", [])
    if index < 0 or index >= len(segments):
        raise HTTPException(status_code=404, detail=f"세그먼트 인덱스 범위 초과 (0~{len(segments) - 1})")

    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text는 비어있을 수 없습니다.")

    segments[index]["text"] = text
    segments[index]["user_edited"] = True

    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {"status": "success", "meeting_id": meeting_id, "segment": segments[index]}


@router.post("/meetings/{meeting_id}/refine")
async def refine_meeting_endpoint(meeting_id: str, request: Request):
    """
    정밀 재분석 수동 트리거 — 회의 종료 시 자동 실행되지만,
    자동 실행이 실패했거나 (서버 재시작 등) 예전 회의를 다시 분석하고 싶을 때 사용.
    무거운 GPU 작업이라 완료까지 시간이 걸릴 수 있음 (회의 길이에 비례).
    """
    _validate_meeting_id(meeting_id)
    if not os.path.isfile(os.path.join(MEETINGS_DIR, meeting_id, "transcript.json")):
        raise HTTPException(status_code=404, detail="해당 회의록을 찾을 수 없습니다.")

    meta = await refine_meeting(meeting_id, request.app.state)
    if meta is None:
        raise HTTPException(status_code=500, detail="정밀 재분석 실패 — 서버 로그 확인 필요")
    return {
        "status": "success",
        "meeting_id": meeting_id,
        "refined": meta.get("refined", False),
        "segment_count": len(meta.get("segments", [])),
    }
