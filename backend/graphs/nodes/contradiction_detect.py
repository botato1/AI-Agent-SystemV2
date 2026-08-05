# backend/graphs/nodes/contradiction_detect.py

# 회의 발화(meeting_segment) 또는 채팅 메시지(room_message) 하나가
# 업로드 문서(DOCUMENT_COLLECTION)와 모순되는지 감지하는 노드.
#
# 처리 순서: 문서 컬렉션 유사 검색 -> LLM 모순 판단 -> 쿨다운 체크 -> 저장
# (v2 스펙 10.1 처리 흐름과 동일)

import json
import math
import uuid

import httpx

from backend.db.crud import content_chunk_crud, contradiction_crud
from backend.db.session import SessionLocal
from backend.graphs.states.contradiction_state import (
    ContradictionState,
    DetectedContradiction,
)
from backend.modules.llm.ollama_client import OLLAMA_MODEL_LIGHT, _call_ollama
from backend.modules.rag.chroma_client import DOCUMENT_COLLECTION, search_hybrid

# [수정] 자체 OLLAMA_BASE_URL/OLLAMA_MODEL 선언과 httpx 직접 호출을 걷어내고
# 공용 ollama_client를 쓴다 (승주 리뷰 반영, ai_chat_answer.py와 동일한 정리).
# - 독자 선언한 OLLAMA_MODEL 환경변수가 공용 OLLAMA_MODEL_LIGHT/HEAVY와 어긋날 수 있었음
# - _call_ollama()를 거치면 다른 노드와 동일하게 중국어 감지 자동 재시도가 적용된다
#   (기존엔 httpx.post 직접 호출이라 이 안전장치가 빠져있었음)
# format:json은 응답을 JSON으로 파싱하는 이 노드에 필요한 보장이라, 공용 함수에
# response_format 인자를 추가해서 그대로 유지한다.
CONTRADICTION_JUDGE_MODEL = OLLAMA_MODEL_LIGHT

TOP_K_CANDIDATES = 5
# 이 미만이면 LLM이 "모순"이라고 답해도 저장/알림 대상에서 완전히 제외한다.
CONFIDENCE_THRESHOLD = 0.6

# 검색 후보 중 이 하이브리드 유사도 미만인 청크는 아예 LLM 판정에 넘기지 않는다.
# (무관한 문서 조각이 어쩌다 confidence threshold를 넘겨 오탐이 나는 것을 원천 차단.
#  rag_service.py의 실측 기준 "관련있음 0.6~, 무관 0.4 미만"과 동일한 값 사용.)
RELEVANCE_THRESHOLD = 0.4

_JUDGE_PROMPT = """당신은 팀 문서와 회의/채팅 발언 사이의 모순을 판단하는 검토자입니다.

[발언]
{statement}

[문서 근거]
{reference}

이 발언이 문서 내용과 명백히 충돌하는지 판단하세요.

[모순이 아닌 경우 — is_contradiction=false]
- 같은 주제를 다른 각도에서 언급하거나 문서 내용을 그대로 반복/부연하는 경우
- 새로운 사실·수치·방침 주장이 없는 단순 찬반·제안 거절·동의·질문
  (예: "굳이 바꿀 필요 있나요? 기존 방식대로 가시죠" 처럼 새 주장 없이 현행 유지에 동의하는 발언)

[severity 기준 — is_contradiction=true일 때만]
- high  : 숫자·날짜·금액·담당자 등 사실이 문서와 직접 충돌
- medium: 방침·방향·결정 내용이 상충
- low   : 뉘앙스·표현 차이 수준

반드시 아래 JSON 형식으로만 답하세요. 다른 설명은 절대 덧붙이지 마세요.

{{
  "is_contradiction": true 또는 false,
  "reason": "판단 이유를 한 문장으로",
  "severity": "low" 또는 "medium" 또는 "high",
  "confidence": 0.0에서 1.0 사이 숫자
}}"""


def _judge_contradiction(statement: str, reference: str) -> dict:
    """LLM에게 발언과 근거 구절을 비교시켜 모순 여부를 JSON으로 받는다."""
    prompt = _JUDGE_PROMPT.format(statement=statement, reference=reference)

    try:
        raw_text = _call_ollama(
            prompt,
            timeout=60.0,
            model=CONTRADICTION_JUDGE_MODEL,
            response_format="json",
        ).strip()
        parsed = json.loads(raw_text)

        if not isinstance(parsed, dict):
            raise ValueError(f"응답이 JSON 객체가 아님: {parsed!r}")

        severity = parsed.get("severity")
        if severity not in ("low", "medium", "high"):
            print(f"[contradiction_detect] 알 수 없는 severity 값, medium으로 대체: {severity!r}")
            severity = "medium"

        is_contradiction = parsed.get("is_contradiction")
        if not isinstance(is_contradiction, bool):
            # bool("false")는 True라서, 문자열로 온 경우 그대로 신뢰하면 안 됨
            raise ValueError(f"is_contradiction이 boolean이 아님: {is_contradiction!r}")

        confidence = float(parsed.get("confidence", 0.0))
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence 범위가 올바르지 않음: {confidence!r}")

        return {
            "is_contradiction": is_contradiction,
            "reason": str(parsed.get("reason", "")),
            "severity": severity,
            "confidence": confidence,
        }
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
        print(f"[contradiction_detect] LLM 판단 실패: {repr(e)}")
        return {"is_contradiction": False, "reason": "", "severity": "low", "confidence": 0.0}


def contradiction_detect_node(state: ContradictionState) -> dict:
    workspace_id = state["workspace_id"]
    category_id = state["category_id"]
    statement_text = state["statement_text"]
    source_type = state["source_type"]

    if source_type not in ("meeting_segment", "room_message"):
        return {"error": f"알 수 없는 source_type: {source_type!r}"}

    source_id = state.get("meeting_segment_id") if source_type == "meeting_segment" else state.get("room_message_id")

    if not source_id:
        return {"error": f"source_type={source_type}에 맞는 원본 ID가 state에 없습니다."}

    workspace_uuid = uuid.UUID(workspace_id)
    category_uuid = uuid.UUID(category_id)
    source_uuid = uuid.UUID(source_id)

    try:
        candidates = search_hybrid(
            query_text=statement_text,
            workspace_id=workspace_id,
            category_id=category_id,
            top_k=TOP_K_CANDIDATES,
            collection_name=DOCUMENT_COLLECTION,
        )
    except Exception as e:
        return {"error": f"문서 유사 검색 실패: {repr(e)}"}

    # 관련도 필터: 유사도가 낮은(무관한) 후보는 LLM 판정 전에 제거한다.
    # 이게 없으면 무관한 문서 조각이 어쩌다 confidence threshold를 넘겨 오탐이 난다.
    candidates = [c for c in candidates if c.get("score", 0.0) >= RELEVANCE_THRESHOLD]

    if not candidates:
        return {
            "content_chunk_candidates": [],
            "llm_judgments": [],
            "detected_contradictions": [],
            "saved_contradiction_ids": [],
        }

    db = SessionLocal()
    llm_judgments: list[dict] = []

    try:
        # 1단계: 후보를 모두 판정만 하고, 통과한 것들을 모아둔다 (아직 저장하지 않음).
        #   같은 발언에 대해 유사한 청크 여러 개가 각각 모순 판정되면 카드가 중복 저장되던 문제 →
        #   판정을 다 모은 뒤 confidence가 가장 높은 하나만 저장한다 (발언당 모순 카드 1개).
        passed: list[tuple] = []  # (judgment, chunk)
        for candidate in candidates:
            chunk = content_chunk_crud.get_chunk_by_chroma_id(db, candidate["id"])
            if not chunk:
                # ChromaDB엔 있는데 Postgres 쪽 원본 청크가 없는 경우(고아 데이터) — 스킵
                continue

            judgment = _judge_contradiction(statement_text, chunk.chunk_text)
            llm_judgments.append({"chunk_id": str(chunk.id), **judgment})

            if not judgment["is_contradiction"] or judgment["confidence"] < CONFIDENCE_THRESHOLD:
                continue

            passed.append((judgment, chunk))

        if not passed:
            return {
                "content_chunk_candidates": candidates,
                "llm_judgments": llm_judgments,
                "detected_contradictions": [],
                "saved_contradiction_ids": [],
            }

        # 2단계: confidence 최고 1개만 채택.
        best_judgment, best_chunk = max(passed, key=lambda pj: pj[0]["confidence"])

        # dedup_key는 (발언, 근거 파일) 단위로 만든다 — 청크가 달라도 같은 발언·같은 문서면
        # 동일 키로 취급해 재판정 시 중복 저장/알림을 막는다.
        dedup_key = contradiction_crud.make_deduplication_key(
            source_type=source_type,
            source_id=source_uuid,
            reference_file_id=best_chunk.file_id,
            reference_id=best_chunk.file_id,
        )

        detected: list[DetectedContradiction] = []
        saved_ids: list[str] = []

        if not contradiction_crud.is_in_cooldown(db, workspace_uuid, dedup_key):
            detected.append({
                "reference_type": "content_chunk",
                "reference_file_id": str(best_chunk.file_id),
                "reference_chunk_id": str(best_chunk.id),
                "reason": best_judgment["reason"],
                "confidence_score": best_judgment["confidence"],
                "severity": best_judgment["severity"],
                "deduplication_key": dedup_key,
            })

            source_field = {
                "meeting_segment": "meeting_segment_id",
                "room_message": "room_message_id",
            }[source_type]

            row = contradiction_crud.create_contradiction(
                db,
                workspace_id=workspace_uuid,
                category_id=category_uuid,
                source_type=source_type,
                reference_type="content_chunk",
                reference_file_id=best_chunk.file_id,
                statement_text_snapshot=statement_text,
                reference_text_snapshot=best_chunk.chunk_text,
                confidence_score=best_judgment["confidence"],
                deduplication_key=dedup_key,
                severity=best_judgment["severity"],
                reason=best_judgment["reason"],
                reference_chunk_id=best_chunk.id,
                **{source_field: source_uuid},
            )
            saved_ids.append(str(row.id))
    finally:
        db.close()

    return {
        "content_chunk_candidates": candidates,
        "llm_judgments": llm_judgments,
        "detected_contradictions": detected,
        "saved_contradiction_ids": saved_ids,
    }
