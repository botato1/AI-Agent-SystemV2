# backend/services/similarity_service.py

"""문서 유사도 그래프뷰 계산 서비스."""

import uuid

from sqlalchemy.orm import Session

from backend.db.crud import file_crud, similarity_crud
from backend.db.session import SessionLocal
from backend.modules.rag.chroma_client import DOCUMENT_COLLECTION, get_or_create_collection

MIN_STORAGE_SCORE = 0.3  # 이 미만은 저장도 안 함 (테이블 비대화 방지)


# TODO: chroma_client.py로 이관 필요 (승주 확인 후). 지금은 승주가 당장
# 작업 못 하는 상황이라, chroma_client.py의 공개 함수(get_or_create_collection,
# DOCUMENT_COLLECTION)만 사용해 우회 구현한다. 나중에 정식으로 chroma_client.py에
# get_document_embedding()으로 옮기고 여기서는 그 함수를 호출하는 걸로 정리할 것.
def _get_document_embedding(document_id: str, workspace_id: str) -> list[float] | None:
    """DOCUMENT_COLLECTION에서 해당 문서의 청크 임베딩들을 평균(mean pooling)한다."""
    collection = get_or_create_collection(DOCUMENT_COLLECTION)
    result = collection.get(
        where={"$and": [{"document_id": document_id}, {"workspace_id": workspace_id}]},
        include=["embeddings"],
    )
    embeddings = result.get("embeddings")
    if embeddings is None or len(embeddings) == 0:
        return None
    dim = len(embeddings[0])
    return [sum(vec[i] for vec in embeddings) / len(embeddings) for i in range(dim)]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def compute_similarities_for_document(
    db: Session, workspace_id: uuid.UUID, file_id: uuid.UUID
) -> None:
    """새로 분석 완료된 문서와 기존 그래프 대상 문서들의 유사도를 계산해 저장한다."""
    new_vector = _get_document_embedding(str(file_id), str(workspace_id))
    if new_vector is None:
        return

    for other in file_crud.list_graph_eligible_files(db, workspace_id, exclude_file_id=file_id):
        other_vector = _get_document_embedding(str(other.id), str(workspace_id))
        if other_vector is None:
            continue
        score = _cosine_similarity(new_vector, other_vector)
        if score >= MIN_STORAGE_SCORE:
            similarity_crud.upsert_similarity(db, workspace_id, file_id, other.id, score)


def compute_similarities_for_document_background(workspace_id: uuid.UUID, file_id: uuid.UUID) -> None:
    """백그라운드 실행용 — 요청 스코프 세션이 이미 닫혔을 수 있어 자체 세션을 새로 연다."""
    db = SessionLocal()
    try:
        compute_similarities_for_document(db, workspace_id, file_id)
    except Exception as e:
        print(f"[similarity_service] 유사도 계산 실패: file_id={file_id}, error={repr(e)}")
    finally:
        db.close()