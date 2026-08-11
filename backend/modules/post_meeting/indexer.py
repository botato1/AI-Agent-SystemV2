"""post-meeting 파이프라인 2-5: 검색용 인덱싱 (이중 저장)

1) 회의 원문 청킹 → content_chunks + MEETING_COLLECTION  (document_loader 재사용)
2) 새로 active가 된 decision → DECISION_COLLECTION (통째로 1개 벡터, 크기 기반 청킹 안 함)
3) AI Chat 근거 제공용 연결 - content_chunks.metadata_json.related_decision_ids 관례
"""

import uuid

from sqlalchemy.orm import Session

from backend.db.modules import Decision
from backend.modules.rag import chroma_client
from backend.modules.rag.document_loader import load_document


def index_transcript(
    db: Session,
    file_id: uuid.UUID,
    transcription: list[dict],
) -> dict:
    """
    [수정 - 리뷰 반영] 기존에는 평문 텍스트를 받아서 줄 단위로 다시 쪼개며
    start=end=0.0으로 채웠는데, 이러면 MeetingSegment의 실제 타임스탬프가
    사라진다. 이제 text_assembler.get_segments_for_indexing()이 만든
    구조화된 리스트(실제 초 단위 타임스탬프 포함)를 그대로 받아서
    document_loader에 넘긴다 - 재파싱 자체가 필요 없어짐.
    """
    return load_document(db, file_id, transcription=transcription)


def index_decisions(
    db: Session,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    decisions: list[Decision],
) -> int:
    """
    새로 active가 된 decision들을 DECISION_COLLECTION에 벡터로 저장.
    decision_text(+reason)를 통째로 1개 벡터로 저장한다 - 이미 짧게 정리된
    텍스트라 content_chunks처럼 크기 기반으로 쪼갤 필요가 없다 (설계 문서 참조).

    [수정 - decision_transition.py의 pending→active 전이 추가하며 발견] 이 함수는
    원래 "새로 db.add()된, 아직 Chroma에 없는 decision"만 받는다는 전제로
    insert_document()(내부적으로 collection.add() 사용, upsert 아님)를 그대로
    호출했다. pending→active 전이는 이미 Chroma에 pending 상태 텍스트로 색인된
    "기존" decision을 내용만 바꿔서 다시 넘기므로, add()가 중복 id를 만나 실패하거나
    (버전에 따라) 조용히 무시되어 오래된 pending 텍스트가 Chroma에 그대로 남는
    문제가 있었다. insert 전에 항상 delete_document()로 먼저 지우도록 해서
    upsert처럼 동작하게 한다 - 새 decision(아직 없음)엔 안전한 no-op이고,
    기존 decision(이미 있음)엔 실제로 갱신되게 한다.
    """
    saved = 0
    for decision in decisions:
        content = decision.decision_text
        if decision.reason:
            content = f"{content}\n{decision.reason}"

        chroma_client.delete_document(
            str(decision.id), str(workspace_id), collection_name=chroma_client.DECISION_COLLECTION
        )
        chroma_client.insert_document({
            "id": str(decision.id),
            "content": content,
            "workspace_id": str(workspace_id),
            "category_id": str(category_id),
            "document_id": str(decision.id),
            "upload_context": "decision",
            "title": decision.title,
        })
        saved += 1

    return saved


def tag_chunks_with_decisions(
    db: Session,
    file_id: uuid.UUID,
    decisions: list[Decision],
    commit: bool = True,
) -> None:
    """
    AI Chat 근거 제공용 관례: 이 회의의 content_chunks에
    metadata_json.related_decision_ids를 태깅한다.

    모순 감지에는 쓰지 않는다 (모순 감지는 DECISION_COLLECTION을 직접 검색).
    "왜 그렇게 결정됐어?" 같은 AI Chat 질문에서 decision_text 한 줄로 부족할 때,
    관련 원문 청크까지 같이 찾아서 보여주는 용도.

    [수정 - 리뷰 반영 9번] commit 옵션 추가 (post_meeting 파이프라인 단일 트랜잭션용).
    """
    from backend.db.crud import content_chunk_crud

    if not decisions:
        return

    decision_ids = [str(d.id) for d in decisions]
    chunks = content_chunk_crud.get_chunks_by_file(db, file_id, chunk_type="meeting_segment")
    for chunk in chunks:
        existing_meta = chunk.metadata_json or {}
        existing_meta["related_decision_ids"] = decision_ids
        chunk.metadata_json = existing_meta

    if commit:
        db.commit()
    else:
        db.flush()