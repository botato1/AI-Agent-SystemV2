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
    transcript: str,
) -> dict:
    """
    회의 원문을 청킹해서 content_chunks + MEETING_COLLECTION에 저장한다.
    document_loader.load_document()를 transcription 인자로 호출 -
    이미 화자 라벨이 붙은 [SPEAKER]: 형태 텍스트를 다시 파싱하지 않고,
    발화 단위 리스트로 넘기기 위해 transcript를 줄 단위로 되돌린다.
    """
    lines = transcript.split("\n")
    transcription = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and "]:" in line:
            speaker, text = line.split("]:", 1)
            speaker = speaker.lstrip("[")
            transcription.append({"speaker": speaker, "text": text.strip(), "start": 0.0, "end": 0.0})
        else:
            transcription.append({"speaker": "SPEAKER_00", "text": line, "start": 0.0, "end": 0.0})

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
    """
    saved = 0
    for decision in decisions:
        content = decision.decision_text
        if decision.reason:
            content = f"{content}\n{decision.reason}"

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
) -> None:
    """
    AI Chat 근거 제공용 관례: 이 회의의 content_chunks에
    metadata_json.related_decision_ids를 태깅한다.

    모순 감지에는 쓰지 않는다 (모순 감지는 DECISION_COLLECTION을 직접 검색).
    "왜 그렇게 결정됐어?" 같은 AI Chat 질문에서 decision_text 한 줄로 부족할 때,
    관련 원문 청크까지 같이 찾아서 보여주는 용도.
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

    db.commit()