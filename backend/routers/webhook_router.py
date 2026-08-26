# backend/routers/webhook_router.py

"""외부 서버(STT 8002)가 보내는 웹훅 수신 전용 라우터.
사용자 인증(JWT) 대신 공유 시크릿 헤더로 검증한다."""

import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.crud import meeting_crud
from backend.db.session import get_db
from backend.services import meeting_service

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
    background_tasks: BackgroundTasks,
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
        # session_id 재사용 시 STT 서버 쪽 meeting_id가 여러 개 생길 수 있어서, 웹훅으로
        # 받을 때마다 최신 meeting_id를 저장해둔다 - 수동 재분석 시 이 값을 우선 사용한다.
        meeting_crud.update_meeting_info(db, meeting_id, stt_meeting_id=payload.meeting_id)
        try:
            refined_data = meeting_service.fetch_refined_transcript(payload.meeting_id)
            print(f"[webhook] 재분석 세그먼트 {len(refined_data.get('segments', []))}개 조회 완료")
            # 요약 재생성은 LLM 호출이 걸리는 작업이라 웹훅 응답을 막지 않도록 백그라운드로 실행.
            # meeting_postprocess_node는 재호출하지 않는다 - 함수 자체 docstring 참조.
            background_tasks.add_task(
                meeting_service.regenerate_summary_from_refined_transcript,
                meeting_id=payload.session_id,
                refined_data=refined_data,
            )
        except Exception as e:
            print(f"[webhook] 재분석 결과 조회 실패: {repr(e)}")
    else:
        print(f"[webhook] 정밀 재분석 실패: meeting_id={meeting_id} - 이미 실시간 결과로 처리 완료됨")

    return