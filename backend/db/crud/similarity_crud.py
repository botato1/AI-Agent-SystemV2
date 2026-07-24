"""문서 유사도(그래프뷰) CRUD — 내 파트"""

import uuid

from sqlalchemy.orm import Session

from backend.db.modules import FileSimilarity


def _normalize_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """작은 UUID를 source, 큰 UUID를 target으로 — 중복 방향 저장 방지."""
    return (a, b) if str(a) < str(b) else (b, a)


def upsert_similarity(
    db: Session,
    workspace_id: uuid.UUID,
    file_id_a: uuid.UUID,
    file_id_b: uuid.UUID,
    score: float,
    embedding_model: str | None = None,
) -> FileSimilarity:
    source_id, target_id = _normalize_pair(file_id_a, file_id_b)
    row = (
        db.query(FileSimilarity)
        .filter(
            FileSimilarity.source_file_id == source_id,
            FileSimilarity.target_file_id == target_id,
        )
        .first()
    )
    if row:
        row.similarity_score = score
        row.embedding_model = embedding_model
    else:
        row = FileSimilarity(
            workspace_id=workspace_id,
            source_file_id=source_id,
            target_file_id=target_id,
            similarity_score=score,
            embedding_model=embedding_model,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_similarities_for_workspace(
    db: Session, workspace_id: uuid.UUID, min_score: float = 0.5
) -> list[FileSimilarity]:
    """그래프뷰 렌더링용. threshold 이상만 엣지로 반환."""
    return (
        db.query(FileSimilarity)
        .filter(
            FileSimilarity.workspace_id == workspace_id,
            FileSimilarity.similarity_score >= min_score,
        )
        .all()
    )

def delete_similarities_for_file(db: Session, file_id: uuid.UUID) -> None:
    """문서 삭제/재분석 시 관련 유사도 row를 정리한다."""
    db.query(FileSimilarity).filter(
        (FileSimilarity.source_file_id == file_id) | (FileSimilarity.target_file_id == file_id)
    ).delete(synchronize_session=False)
    db.commit()