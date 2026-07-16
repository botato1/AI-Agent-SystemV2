"""실시간 판단 파이프라인 1-2: 문서 기반 모순 감지 · 추천

decision_judgment.judge()가 "none"(DECISION_COLLECTION 매칭 없음)을 반환했을 때,
또는 애초에 정적 자료 관련 발화일 때 도는 경로. 과거 결정과는 무관하게, 지금
유효한 문서 자체와 비교한다.

[MVP 스코프] 코드 분석(tree-sitter, code_symbols/code_facts)이 아직 구현 확정
전이라, 이번 스코프는 문서(content_chunks, chunk_type='document_text') 비교만
구현한다. code_facts 검색은 함수 스텁만 남겨두고 실제 로직은 비워둔다 - 코드
분석 파이프라인이 확정되면 그때 채운다.
"""

import json
import uuid

from sqlalchemy.orm import Session

from backend.db.crud import contradiction_crud, file_crud, history_crud
from backend.modules.llm.ollama_client import _call_ollama
from backend.modules.rag import chroma_client

CONTRADICTION_MATCH_THRESHOLD = 0.65  # TBD - 실험 후 조정. 이 아래는 모순 검토할 가치도 없을 만큼 무관.
CONTRADICTION_POPUP_THRESHOLD = 0.6

JUDGMENT_PROMPT_TEMPLATE = """아래는 방금 나온 발화와, 그것과 의미적으로 유사한 문서 내용이다.
이 발화가 문서 내용과 실제로 충돌하는지 판단해서 JSON으로만 답하라.

[문서 내용]
{document_content}
(출처: {filename})

[방금 발화]
{statement}

[출력 JSON]
{{
  "is_contradiction": true/false,
  "confidence": 0.0
}}
"""


def _find_code_facts_match(statement: str) -> None:
    """
    [스텁 - 코드 분석 파이프라인 확정 후 구현]
    fact_type/key 매칭 → 필드 일치 비교(exact match)로 포트번호, DB종류 등 확인.
    지금은 항상 None을 반환해 이 경로가 스킵되게 한다.
    """
    return None


def _judge_document_contradiction(document_content: str, filename: str, statement: str) -> dict:
    prompt = JUDGMENT_PROMPT_TEMPLATE.format(
        document_content=document_content, filename=filename, statement=statement
    )
    raw = _call_ollama(prompt, timeout=60.0)
    try:
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start : end + 1])
        parsed.setdefault("is_contradiction", False)
        parsed.setdefault("confidence", 0.0)
        return parsed
    except (json.JSONDecodeError, ValueError):
        return {"is_contradiction": False, "confidence": 0.0}


def judge(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    source_type: str,  # 'meeting_segment' | 'room_message'
    source_id: uuid.UUID,
    statement: str,
    session_meeting_id: uuid.UUID | None = None,
    session_room_id: uuid.UUID | None = None,
) -> dict:
    """
    decision_judgment.judge()가 "none"을 반환했을 때 이어서 호출.

    Returns:
        {"case": "contradiction"|"recommendation"|"none", "popup": dict|None}
    """
    session_kwargs = {"session_meeting_id": session_meeting_id, "session_room_id": session_room_id}

    # [스텁] code_facts 경로 - 코드 분석 파이프라인 확정 전까지 항상 스킵됨
    code_fact_match = _find_code_facts_match(statement)
    if code_fact_match is not None:
        # TODO: 코드 분석 파이프라인 확정 후 여기서 값 비교 → 모순 후보 생성
        pass

    # 문서(content_chunks, chunk_type='document_text') 검색
    # MVP 스코프: 코드/설정 청크는 대상에서 제외 (document_text만)
    results = chroma_client.search_hybrid(
        query_text=statement,
        workspace_id=str(workspace_id),
        category_id=str(category_id),
        top_k=5,
        collection_name=chroma_client.DOCUMENT_COLLECTION,
    )
    if not results:
        return {"case": "none", "popup": None}

    top = results[0]
    file_id_str = top.get("document_id")
    if not file_id_str:
        return {"case": "none", "popup": None}

    file_id = uuid.UUID(file_id_str)
    file_row = file_crud.get_file(db, file_id)
    if not file_row:
        return {"case": "none", "popup": None}

    # threshold 미만이면 관련도 자체가 낮아 모순 검토할 가치도 없음
    if top["score"] < CONTRADICTION_MATCH_THRESHOLD:
        return {"case": "none", "popup": None}

    # [수정 - 2026.07.16] 벡터 유사도는 "관련 있어 보이는 후보"를 좁히는 역할일 뿐,
    # "충돌하는지"는 별개 판단이라 LLM이 내용을 읽고 한 번 더 확인해야 한다
    # (유사도 높다고 곧 모순은 아님 - 예: "API 응답 속도" 발화와 "API 응답 포맷: JSON"
    # 문서는 유사도는 높아도 충돌하는 내용이 아님).
    #
    # 기존에는 모순 판단(threshold 0.65)과 추천 판단(threshold 0.8)을 별도 숫자로
    # 나눠서, LLM이 "모순 아님"이라고 판단해도 유사도가 0.65~0.8 사이면 추천도 안 뜨고
    # 사라지는 구멍이 있었음. 지금은 "모순 판단까지 갔다가 아니라고 나온 것 = 그 자체로
    # 추천 대상"으로 자연스럽게 이어지도록 통일 - 별도 RECOMMENDATION_MATCH_THRESHOLD 불필요.
    judgment = _judge_document_contradiction(top["content"], file_row.original_filename, statement)

    if judgment["is_contradiction"] and judgment["confidence"] >= CONTRADICTION_POPUP_THRESHOLD:
        dedup_key = contradiction_crud.make_deduplication_key(
            source_type, source_id, file_id, file_id
        )
        if not contradiction_crud.is_in_cooldown(db, workspace_id, dedup_key):
            contradiction = contradiction_crud.create_contradiction(
                db,
                workspace_id=workspace_id, category_id=category_id,
                source_type=source_type, reference_type="content_chunk",
                reference_file_id=file_id,
                statement_text_snapshot=statement,
                reference_text_snapshot=top["content"],
                confidence_score=judgment["confidence"],
                deduplication_key=dedup_key,
                **session_kwargs,
                **({"meeting_segment_id": source_id} if source_type == "meeting_segment"
                   else {"room_message_id": source_id}),
            )
            return {
                "case": "contradiction",
                "popup": {
                    "type": "contradiction",
                    "message": f"'{statement}'이(가) 업로드된 {file_row.original_filename}의"
                               f" 내용과 다릅니다",
                    "contradiction_id": str(contradiction.id),
                    "actions": ["change_acknowledged", "keep_reference"],
                },
            }
        # 쿨다운 중이면 팝업 없이 종료 (같은 모순 반복 알림 방지)
        return {"case": "contradiction", "popup": None}

    # 모순은 아니지만 관련은 있었던 경우 → 문서 추천으로 이어짐
    already_shown = history_crud.already_notified_in_session(
        db, reference_file_id=file_id, **session_kwargs
    )
    if already_shown:
        return {"case": "recommendation", "popup": None}

    history_crud.record_match(
        db,
        workspace_id=workspace_id, category_id=category_id,
        source_type=source_type, match_type="document_recommendation",
        reference_file_id=file_id, confidence_score=top["score"],
        **session_kwargs,
    )
    return {
        "case": "recommendation",
        "popup": {
            "type": "document_recommendation",
            "message": f"'{statement[:30]}' 관련 문서를 찾았습니다: {file_row.original_filename}",
        },
    }