# backend/graphs/nodes/contradiction_detect.py

# 회의 발화(meeting_segment) 또는 채팅 메시지(room_message) 하나가
# 업로드 문서(DOCUMENT_COLLECTION)와 모순되는지 감지하는 노드.
#
# 처리 순서: 문서 컬렉션 유사 검색 -> LLM 모순 판단 -> 쿨다운 체크 -> 저장
# (v2 스펙 10.1 처리 흐름과 동일)

import json
import os
import uuid

import httpx

from backend.db.crud import content_chunk_crud, contradiction_crud
from backend.db.session import SessionLocal
from backend.graphs.states.contradiction_state import (
    ContradictionState,
    DetectedContradiction,
)
from backend.modules.rag.chroma_client import DOCUMENT_COLLECTION, search_hybrid

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

TOP_K_CANDIDATES = 5
# 이 미만은 LLM이 "모순"이라고 답해도 알림까지 보내지 않는다.
CONFIDENCE_THRESHOLD = 0.6

_JUDGE_PROMPT = """당신은 팀 문서와 회의/채팅 발언 사이의 모순을 판단하는 검토자입니다.

[발언]
{statement}

[문서 근거]
{reference}

이 발언이 문서 내용과 명백히 충돌하는지 판단하세요.
같은 주제를 다른 각도에서 언급하거나 문서 내용을 그대로 반복/부연하는 경우는 모순이 아닙니다.
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
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            timeout=60.0,
        )
        response.raise_for_status()
        raw_text = response.json().get("response", "").strip()
        parsed = json.loads(raw_text)
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        print(f"[contradiction_detect] LLM 판단 실패: {repr(e)}")
        return {"is_contradiction": False, "reason": "", "severity": "low", "confidence": 0.0}

    severity = parsed.get("severity")
    if severity not in ("low", "medium", "high"):
        severity = "medium"

    return {
        "is_contradiction": bool(parsed.get("is_contradiction", False)),
        "reason": str(parsed.get("reason", "")),
        "severity": severity,
        "confidence": float(parsed.get("confidence", 0.0)),
    }


def contradiction_detect_node(state: ContradictionState) -> dict:
    workspace_id = state["workspace_id"]
    category_id = state["category_id"]
    statement_text = state["statement_text"]
    source_type = state["source_type"]
    source_id = state.get("meeting_segment_id") if source_type == "meeting_segment" else state.get("room_message_id")

    if not source_id:
        return {"error": f"source_type={source_type}에 맞는 원본 ID가 state에 없습니다."}

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

    if not candidates:
        return {
            "content_chunk_candidates": [],
            "llm_judgments": [],
            "detected_contradictions": [],
            "saved_contradiction_ids": [],
        }

    db = SessionLocal()
    llm_judgments: list[dict] = []
    detected: list[DetectedContradiction] = []
    saved_ids: list[str] = []

    try:
        for candidate in candidates:
            chunk = content_chunk_crud.get_chunk_by_chroma_id(db, candidate["id"])
            if not chunk:
                # ChromaDB엔 있는데 Postgres 쪽 원본 청크가 없는 경우(고아 데이터) — 스킵
                continue

            judgment = _judge_contradiction(statement_text, chunk.chunk_text)
            llm_judgments.append({"chunk_id": str(chunk.id), **judgment})

            if not judgment["is_contradiction"] or judgment["confidence"] < CONFIDENCE_THRESHOLD:
                continue

            dedup_key = contradiction_crud.make_deduplication_key(
                source_type=source_type,
                source_id=uuid.UUID(source_id),
                reference_file_id=chunk.file_id,
                reference_id=chunk.id,
            )

            if contradiction_crud.is_in_cooldown(db, uuid.UUID(workspace_id), dedup_key):
                continue

            detected.append({
                "reference_type": "content_chunk",
                "reference_file_id": str(chunk.file_id),
                "reference_chunk_id": str(chunk.id),
                "reason": judgment["reason"],
                "confidence_score": judgment["confidence"],
                "severity": judgment["severity"],
                "deduplication_key": dedup_key,
            })

            source_field = {
                "meeting_segment": "meeting_segment_id",
                "room_message": "room_message_id",
            }[source_type]

            row = contradiction_crud.create_contradiction(
                db,
                workspace_id=uuid.UUID(workspace_id),
                category_id=uuid.UUID(category_id),
                source_type=source_type,
                reference_type="content_chunk",
                reference_file_id=chunk.file_id,
                statement_text_snapshot=statement_text,
                reference_text_snapshot=chunk.chunk_text,
                confidence_score=judgment["confidence"],
                deduplication_key=dedup_key,
                severity=judgment["severity"],
                reason=judgment["reason"],
                reference_chunk_id=chunk.id,
                **{source_field: uuid.UUID(source_id)},
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
