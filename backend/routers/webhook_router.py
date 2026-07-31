# backend/routers/webhook_router.py

"""외부 서버(STT 8002)가 보내는 웹훅 수신 전용 라우터.
사용자 인증(JWT) 대신 공유 시크릿 헤더로 검증한다."""

import os
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.crud import meeting_crud
from backend.db.session import get_db

router = APIRouter(prefix="/internal", tags=["Internal Webhook"])

REFINE_WEBHOOK_SECRET = os.getenv("REFINE_WEBHOOK_SECRET", "")


class SttRefineWebhookPayload(BaseModel):
    meeting_id: str
    session_id: str
    refined_at: str | None = None
    segment_count: int
    status: str  # "refined" | "failed"


def _verify_webhook_secret(x_webhook_secret: str | None = Header(default=None)):
    if not REFINE_WEBHOOK_SECRET or x_webhook_secret != REFINE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="웹훅 인증에 실패했습니다.",
        )


@router.post("/stt-refine-webhook", status_code=status.HTTP_204_NO_CONTENT)
def stt_refine_webhook(
    payload: SttRefineWebhookPayload,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_webhook_secret),
):
    try:
        meeting_id = uuid.UUID(payload.session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id가 올바른 회의 ID 형식이 아닙니다.",
        )

    meeting = meeting_crud.get_meeting(db, meeting_id)
    if not meeting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"meeting_id={meeting_id} 회의를 찾을 수 없습니다.",
        )

    if payload.status == "refined":
        print(
            f"[webhook] 정밀 재분석 완료: meeting_id={meeting_id}, "
            f"refined_at={payload.refined_at}, segment_count={payload.segment_count}"
        )
        # TODO: 8002 GET /api/meetings/{id}로 재분석 결과 가져와서
        # 시간 기준 세그먼트 매칭 후 후처리 트리거 (가동현 확인 후 반영)
    else:
        print(f"[webhook] 정밀 재분석 실패: meeting_id={meeting_id} - 실시간 결과로 진행")
        # TODO: 실시간 세그먼트로 후처리 트리거 (아직 트리거 시점 결정 전)

    return