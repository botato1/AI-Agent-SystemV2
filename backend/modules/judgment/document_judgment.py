"""실시간 판단 파이프라인 1-2: 문서 기반 관련 자료 추천

decision_judgment.judge()가 "none"(관련 decision 없음)을 반환했을 때, 발화와 관련된
문서(문서 분석 탭 업로드 자료, document_collection)를 찾아 추천한다.

[수정] 문서 분석 탭 자료는 결정사항이 아니라 참고자료라, 이 내용을 근거로
"모순"을 판단하지 않는다 (기존엔 문서 내용과 발화가 다르면 모순 팝업을 띄웠으나,
참고자료는 애초에 맞고 틀리고를 판단할 대상이 아니라는 게 확인되어 제거함).
문서는 오직 관련 자료 추천에만 쓴다.

[MVP 스코프] code_facts(코드베이스 자체 값과의 사실 비교)는 위 모순판단 제거와
성격이 달라 별도 판단 - tree-sitter 파이프라인 확정 전이라 스텁만 남겨둔다.
"""

import uuid

from sqlalchemy.orm import Session

from backend.db.crud import file_crud, history_crud
from backend.modules.rag import chroma_client

RECOMMENDATION_MATCH_THRESHOLD = 0.65  # TBD - 실험 후 조정. 이 아래는 추천할 가치도 없을 만큼 무관.


def _find_code_facts_match(statement: str) -> None:
    """
    [스텁 - 코드 분석 파이프라인 확정 후 구현]
    fact_type/key 매칭 → 필드 일치 비교(exact match)로 포트번호, DB종류 등 확인.
    지금은 항상 None을 반환해 이 경로가 스킵되게 한다.
    """
    return None


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
        {"case": "recommendation"|"none", "popup": dict|None}
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

    # threshold 미만이면 관련도 자체가 낮아 추천할 가치도 없음
    if top["score"] < RECOMMENDATION_MATCH_THRESHOLD:
        return {"case": "none", "popup": None}

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
