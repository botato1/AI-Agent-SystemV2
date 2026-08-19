# backend/services/judgment_service.py

"""실시간 판단 파이프라인(결정 리마인더/문서 추천/반복논의) 통합 실행.

decision_judgment -> document_judgment -> priority 순서로 판단하고,
팝업이 나오면 Notification으로 저장한다. contradiction 타입은 이미
contradictions 테이블 + 기존 조회 경로로 노출되므로 여기서는 스킵한다.
"""

import json
import re
import uuid

from backend.db.crud import meeting_crud, notification_crud, workspace_crud
from backend.db.session import SessionLocal
from backend.modules.judgment import decision_judgment, document_judgment, priority
from backend.modules.llm.ollama_client import OLLAMA_MODEL_LIGHT, _call_ollama

_SKIP_NOTIFICATION_POPUP_TYPES = {"reasoned_change", "unreasoned_change"}

# [추가 - 팀 논의] Case 0(decision_reminder)은 "처리 대상"이 아닌 FYI성 알림이라
# contradictions 테이블에 합치지 않기로 함(resolve 액션 전제가 안 맞음). 대신
# Notification은 그대로 생성(알림함용)하면서, 추가로 WS push도 같이 할 수 있게
# dict를 반환한다 - 호출부(meeting_ws_router.py/room_ws_router.py)가 judgment_case
# 값 보고 "decision_reminder"면 새 타입으로, 그 외(Case 2/3)면 기존
# "contradiction_alert"로 나눠서 push하는 방식.
_ALSO_PUSH_LIVE_POPUP_TYPES = {"decision_reminder"}

_POPUP_TITLE = {
    "decision_reminder": "이전 결정 리마인더",
    "document_recommendation": "관련 문서 추천",
}

LOW_STT_CONFIDENCE_THRESHOLD = 0.6  # 이 미만이면 판단 자체를 보류 (오탐 방지)


# ── [임시 조치 - 2026.08.10] STT 실시간 세그먼트 병합 대응 ──────────────────
# 실시간 STT가 여러 화자/발화를 하나의 final 세그먼트로 묶어서 보내는 경우가
# 확인됨(원인은 STT 쪽 - 이준오 확인 요청함). 판단 모델은 깨끗한 발화 1개
# 단위로 학습돼서, 여러 문장이 뭉친 텍스트를 그대로 넣으면 판단이 계속
# 헷갈려서 아무 팝업도 안 뜨는 문제가 있었음. STT가 정상화될 때까지, 판단
# 직전에 LLM으로 발화를 분리하는 전처리를 임시로 끼워 넣는다.
#
# TODO: STT 세그먼트 분할이 정상화되면 이 블록(_looks_merged/_split_merged_
# statement/_SPLIT_* 상수)과 run_judgment_pipeline()의 분리 호출 한 줄을
# 삭제하고, statements = [statement_text]로 되돌리면 원래 구조로 복귀됨.
# _judge_single_statement()는 원래 로직 그대로라 그대로 둬도 됨.

_SPLIT_SENTENCE_END_PATTERN = re.compile(r"[.!?다요죠]\s")

_SPLIT_INSTRUCTION = (
    "아래는 실시간 회의에서 STT로 받아적힌 텍스트다. 여러 화자의 여러 발화가 "
    "하나로 뭉쳐 들어왔을 수 있다.\n\n"
    "이 텍스트를 화자/문장 경계 기준으로 개별 발화 단위로 분리하라.\n\n"
    "[규칙]\n"
    "- 원문의 표현을 그대로 유지하고, 내용을 요약하거나 바꾸거나 새로 만들지 마라.\n"
    "- 이미 하나의 발화면 통째로 1개만 반환해라.\n"
    "- 각 항목은 완결된 문장(또는 짧은 구) 단위로 나눠라.\n\n"
    '다음 JSON 배열 형식으로만 답하라: ["발화1", "발화2", ...]'
)


def _looks_merged(text: str) -> bool:
    """문장 종결 패턴이 3개 이상이면 여러 발화가 뭉쳤을 가능성이 있다고 본다.
    짧고 단일한 발화가 훨씬 흔하므로, 의심되는 경우에만 분리 LLM 호출을 태워
    불필요한 지연을 피한다.

    [수정 - 리뷰 반영] 임계값 2 → 3. "9월 22일로 가는 게 안전할 것 같아요. QA
    일정이 부족해서요." 같은 정상적인 "새 값+근거" 한 발화도 문장 종결 패턴이
    2개라 임계값 2에서는 쪼개져버림 - 쪼개지면 근거 문장이 값 제시 문장과
    분리돼 reason_is_clear 판단이 근거를 못 보고 Case 3(근거 없는 변경)로
    오판하거나, 근거만 남은 조각이 presents_new_value=false로 Case 0에
    묻히며 근거 정보가 유실됨. 실제 STT 병합 사례(화면 설계 진행 상황 관련
    여러 화자 발화)는 문장 종결 패턴이 8개였으므로, 3으로 올려도 여유 있게
    잡아내면서 정상적인 2문장 단일 발화 오분리는 피한다."""
    return len(_SPLIT_SENTENCE_END_PATTERN.findall(text)) >= 3


def _split_merged_statement(statement_text: str) -> list[str]:
    """의심되는 경우에만 LLM으로 발화 단위 분리. 실패/미의심 시 원문 그대로 1개."""
    if not _looks_merged(statement_text):
        return [statement_text]

    prompt = f"{_SPLIT_INSTRUCTION}\n\n텍스트:\n{statement_text}"
    try:
        raw = _call_ollama(prompt, timeout=60.0, model=OLLAMA_MODEL_LIGHT,
                            response_format="json", temperature=0)
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed and all(isinstance(s, str) and s.strip() for s in parsed):
            return [s.strip() for s in parsed]
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"[judgment_service] 발화 분리 실패, 원문 그대로 사용: {repr(e)}")

    return [statement_text]

# ── 임시 조치 끝 ──────────────────────────────────────────────────────────


def _judge_single_statement(
    db,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    statement_text: str,
    session_kwargs: dict,
) -> dict | None:
    """발화 1개에 대해 decision_judgment -> document_judgment -> priority를 실행.

    문서추천은 이 함수 안에서 바로 Notification을 생성하고 None을 반환한다.
    Case 2/3(모순)은 Notification 없이 dict만 반환한다(호출부가 실시간 WS push에 씀).
    Case 0(리마인더)은 Notification을 생성하면서 동시에 dict도 반환한다(알림함 +
    실시간 push 둘 다) - _ALSO_PUSH_LIVE_POPUP_TYPES 참조.
    """
    decision_result = decision_judgment.judge(
        db,
        workspace_id=workspace_id,
        category_id=category_id,
        source_type=source_type,
        source_id=source_id,
        statement=statement_text,
        **session_kwargs,
    )

    document_result = None
    if decision_result.get("case") == "none":
        document_result = document_judgment.judge(
            db,
            workspace_id=workspace_id,
            category_id=category_id,
            source_type=source_type,
            source_id=source_id,
            statement=statement_text,
            **session_kwargs,
        )

    popup = priority.select_popup(decision_result, document_result)
    if not popup:
        return None

    if popup["type"] in _SKIP_NOTIFICATION_POPUP_TYPES:
        # [수정 - 라이브 테스트 발견] Case 2/3이 실시간 WS push 하나에만 의존하고
        # 있었는데, 여기까지 오는 데 topic_match+최대 3단계 LLM 호출이 걸려(수 초)
        # 그 사이 WebSocket이 닫히면(회의 일시정지/종료 등) push 자체가
        # RuntimeError("Cannot call 'send' once a close message has been sent.")로
        # 실패하고 - 알림함 폴백도 없어서(원래 "중복이라 생략") 이 판단 결과가
        # 어디에도 안 남고 완전히 유실되는 문제를 실측으로 확인함. Case 0과
        # 동일하게 알림함에도 남겨서, 실시간 push가 실패해도 최소한 알림함에서는
        # 확인 가능하게 한다.
        #
        # notifications.type CHECK 제약에 'reasoned_change'/'unreasoned_change'는
        # 없어서(허용: contradiction_detected/contradiction_resolved/decision_
        # reminder 등) 그대로 못 넣는다 - 의미상 가장 가까운 'contradiction_detected'로
        # 매핑한다(프론트 NotificationBell.tsx가 이미 이 타입을 "회의 도움"으로
        # 처리하고 있어 별도 프론트 수정 없이 바로 뜬다).
        for member, _user in workspace_crud.list_members(db, workspace_id):
            if not notification_crud.is_notification_enabled(db, workspace_id, member.user_id, "contradiction_detected"):
                continue
            notification_crud.create_notification(
                db,
                user_id=member.user_id,
                workspace_id=workspace_id,
                type="contradiction_detected",
                title="결정 변경 감지",
                message=popup["message"],
                ref_type=source_type,
                ref_id=source_id,
            )
        return {
            "contradiction_id": popup["contradiction_id"],
            "message": popup["message"],
            "judgment_case": popup["type"],
            "actions": popup.get("actions", []),
        }

    for member, _user in workspace_crud.list_members(db, workspace_id):
        if not notification_crud.is_notification_enabled(db, workspace_id, member.user_id, popup["type"]):
            continue
        notification_crud.create_notification(
            db,
            user_id=member.user_id,
            workspace_id=workspace_id,
            type=popup["type"],
            title=_POPUP_TITLE.get(popup["type"], "알림"),
            message=popup["message"],
            ref_type=source_type,
            ref_id=source_id,
        )

    if popup["type"] in _ALSO_PUSH_LIVE_POPUP_TYPES:
        # Case 0 - 알림함(Notification, 위에서 생성 완료)과 별개로 실시간 push용
        # dict도 반환. contradiction_id/actions는 없음 - 해결(resolve) 대상이 아님.
        return {
            "message": popup["message"],
            "judgment_case": popup["type"],
            "decision_id": decision_result.get("decision_id"),
        }

    return None


def run_judgment_pipeline(
    *,
    workspace_id: str,
    category_id: str,
    source_type: str,  # "meeting_segment" | "room_message"
    statement_text: str,
    meeting_segment_id: str | None = None,
    room_message_id: str | None = None,
    session_meeting_id: str | None = None,
    session_room_id: str | None = None,
) -> dict | None:
    """발화/메시지 하나마다 백그라운드로 호출한다. 자체 DB 세션을 새로 연다.

    호출부가 실시간 WS push에 쓸 수 있도록 dict를 반환하는 경우:
    - Case 2/3(근거 있는/없는 변경): {"contradiction_id":..., "message":...,
      "judgment_case": "reasoned_change"|"unreasoned_change", "actions":[...]}
    - Case 0(결정 리마인더): {"message":..., "judgment_case": "decision_reminder",
      "decision_id":...} - contradiction_id/actions 없음(해결 대상 아님).
    그 외(문서추천 등)는 Notification만 생성하고 None을 반환한다.
    """
    db = SessionLocal()
    try:
        source_id = uuid.UUID(meeting_segment_id) if meeting_segment_id else uuid.UUID(room_message_id)

        if source_type == "meeting_segment":
            segment = meeting_crud.get_segment(db, source_id)
            if segment and segment.stt_confidence is not None and float(segment.stt_confidence) < LOW_STT_CONFIDENCE_THRESHOLD:
                return None  # STT 신뢰도 낮음 - 모순/리마인더 판단 보류

        session_kwargs = {
            "session_meeting_id": uuid.UUID(session_meeting_id) if session_meeting_id else None,
            "session_room_id": uuid.UUID(session_room_id) if session_room_id else None,
        }

        # [임시 조치] STT가 여러 발화를 하나로 묶어 보내는 경우 대응 - 위 블록 참조.
        # TODO: STT 세그먼트 분할 정상화되면 아래 한 줄을
        #   statements = [statement_text]
        # 로 되돌리면 됨.
        statements = _split_merged_statement(statement_text)

        result = None
        for stmt in statements:
            r = _judge_single_statement(
                db,
                workspace_id=uuid.UUID(workspace_id),
                category_id=uuid.UUID(category_id),
                source_type=source_type,
                source_id=source_id,
                statement_text=stmt,
                session_kwargs=session_kwargs,
            )
            if r and result is None:
                result = r  # 여러 개 중 첫 번째 Case 2/3만 WS push 대상으로 반환
        return result

    except Exception as e:
        print(f"[judgment_service] 판단 파이프라인 실패: {repr(e)}")
        return None
    finally:
        db.close()
