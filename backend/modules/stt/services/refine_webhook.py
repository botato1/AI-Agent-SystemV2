"""
정밀 재분석 완료 알림 웹훅.

왜 필요한가:
  재분석은 회의 종료 후 백그라운드로 돌고, 그 시점에 클라이언트 WebSocket은 이미
  닫혀 있다. 완료를 알릴 통로가 없어서 소비자(백엔드 요약/모순감지 파이프라인)가
  `refined` 플래그를 폴링할 수밖에 없었다. 폴링 대신 완료 시점에 한 번 찔러준다.

전송 실패가 재분석을 망치지 않는다:
  웹훅은 부가 통지이므로 어떤 경우에도 예외를 밖으로 던지지 않는다. 재분석 결과는
  이미 transcript.json에 저장돼 있고, 웹훅이 실패해도 `GET /api/meetings/{id}`로
  받아갈 수 있다.

실패(status="failed")도 통지하는 이유:
  성공만 알리면 재분석이 실패했을 때 소비자가 무한정 기다린다. 실패를 알려주면
  실시간 결과로 폴백할 수 있다.

의존성을 늘리지 않으려고 stdlib urllib을 쓴다 — 요청 하나 보내는 데
httpx/requests를 추가할 이유가 없고, 두 라이브러리 모두 이 프로젝트의
직접 의존성이 아니다(전이 의존성에 기대면 나중에 조용히 깨진다).
"""
import asyncio
import json
import urllib.error
import urllib.request

from ..core.config import (
    logger,
    REFINE_WEBHOOK_URL,
    REFINE_WEBHOOK_TIMEOUT_SEC,
    REFINE_WEBHOOK_RETRIES,
    REFINE_WEBHOOK_RETRY_DELAY_SEC,
    REFINE_WEBHOOK_SECRET,
    REFINE_WEBHOOK_SECRET_HEADER,
)


def _post(url: str, payload: dict, timeout: float) -> int:
    """동기 POST. 블로킹이므로 반드시 executor에서 호출할 것."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if REFINE_WEBHOOK_SECRET:
        headers[REFINE_WEBHOOK_SECRET_HEADER] = REFINE_WEBHOOK_SECRET
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status


async def notify_refine_done(
    meeting_id: str, session_id: str | None,
    refined_at: str | None, segment_count: int, status: str,
) -> None:
    """
    재분석 결과를 소비자에게 통지. 실패해도 조용히 로그만 남긴다.

    payload:
      meeting_id     회의 식별자 ("{session_id}_{timestamp}")
      session_id     클라이언트가 접속 시 넘긴 값 그대로.
                     meeting_id를 파싱해 복원하지 않도록 별도 필드로 준다 —
                     소비자가 meeting_id 포맷에 결합되면 포맷 변경 시 함께 깨진다.
      refined_at     재분석 완료 시각 (ISO 8601, UTC). 실패 시 null
      segment_count  재분석 후 세그먼트 수. ⚠️ 실시간 세그먼트 수와 다를 수 있다
                     (화자 턴 단위로 다시 자르므로) — 인덱스로 매칭하면 어긋난다
      status         "refined" | "failed"
    """
    if not REFINE_WEBHOOK_URL:
        return

    payload = {
        "meeting_id": meeting_id,
        "session_id": session_id,
        "refined_at": refined_at,
        "segment_count": segment_count,
        "status": status,
    }

    for attempt in range(1, REFINE_WEBHOOK_RETRIES + 1):
        try:
            code = await asyncio.to_thread(
                _post, REFINE_WEBHOOK_URL, payload, REFINE_WEBHOOK_TIMEOUT_SEC
            )
            logger.info(f"📬 [{meeting_id}] 재분석 완료 웹훅 전송 (status={status}, HTTP {code})")
            return
        except urllib.error.HTTPError as e:
            # 4xx는 재시도해도 결과가 같다 — 시크릿이 틀렸거나 경로가 잘못된 것이라
            # 사람이 고쳐야 한다. 조용히 3번 반복하면 원인을 못 찾는다.
            if 400 <= e.code < 500:
                logger.error(
                    f"❌ [{meeting_id}] 재분석 완료 웹훅 거부됨 (HTTP {e.code}) — "
                    f"인증 헤더({REFINE_WEBHOOK_SECRET_HEADER})나 URL을 확인할 것. 재시도하지 않음."
                )
                return
            raise
        except Exception as e:
            # 소비자 서버가 재시작 중일 수 있어 몇 번 재시도한다. 통지를 놓치면
            # 소비자 쪽 후처리가 아예 시작되지 않으므로 한 번 실패로 포기하지 않는다.
            last = attempt == REFINE_WEBHOOK_RETRIES
            detail = f"{type(e).__name__}: {e}"
            if last:
                logger.error(
                    f"❌ [{meeting_id}] 재분석 완료 웹훅 전송 실패 ({REFINE_WEBHOOK_RETRIES}회 시도) — {detail}. "
                    f"재분석 결과 자체는 저장돼 있으므로 GET /api/meetings/{meeting_id}로 조회 가능."
                )
                return
            logger.warning(f"⚠️ [{meeting_id}] 웹훅 전송 실패 {attempt}/{REFINE_WEBHOOK_RETRIES} — {detail}")
            await asyncio.sleep(REFINE_WEBHOOK_RETRY_DELAY_SEC * attempt)
