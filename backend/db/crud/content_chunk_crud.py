"""콘텐츠 청크 CRUD (ChromaDB 연결) — 내 파트

PostgreSQL에는 메타데이터+원문만, 임베딩 벡터는 ChromaDB에.
저장 시 항상 두 스토리지가 같이 갱신되도록 상위 서비스 레이어에서
이 함수들과 ChromaDB client.upsert()를 같은 트랜잭션 단위로 묶어 호출할 것.
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import ContentChunk


def create_chunk(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    file_id: uuid.UUID,
    chunk_type: str,
    chunk_index: int,
    chunk_text: str,
    chroma_id: str,
    **extra_fields,
) -> ContentChunk:
    row = ContentChunk(
        workspace_id=workspace_id,
        category_id=category_id,
        file_id=file_id,
        chunk_type=chunk_type,
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        chroma_id=chroma_id,
        **extra_fields,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_chunks_by_file(
    db: Session, file_id: uuid.UUID, chunk_type: Optional[str] = None
) -> list[ContentChunk]:
    q = db.query(ContentChunk).filter(ContentChunk.file_id == file_id)
    if chunk_type:
        q = q.filter(ContentChunk.chunk_type == chunk_type)
    return q.order_by(ContentChunk.chunk_index).all()


def get_chunk_by_chroma_id(db: Session, chroma_id: str) -> Optional[ContentChunk]:
    """ChromaDB 검색 결과(chroma_id)로 PostgreSQL 원본 row를 역참조할 때 사용."""
    return db.query(ContentChunk).filter(ContentChunk.chroma_id == chroma_id).first()


def delete_chunks_by_file(db: Session, file_id: uuid.UUID) -> int:
    """파일 재분석/버전 갱신 시 기존 청크 삭제 (ChromaDB 쪽도 별도로 정리 필요)."""
    count = db.query(ContentChunk).filter(ContentChunk.file_id == file_id).delete()
    db.commit()
    return count


def list_rag_searchable_chunk_files(db: Session, workspace_id: uuid.UUID):
    """
    AI Chat 검색 대상 필터링 기준 조회.
    실제 벡터 검색은 ChromaDB where절로 수행하되(rag_enabled=true, is_latest=true,
    analysis_status=completed), 이 함수는 그 필터 조건에 맞는 file_id 후보를
    PostgreSQL 쪽에서 미리 좁히고 싶을 때 사용.
    """
    from backend.db.modules import WorkspaceFile

    return (
        db.query(WorkspaceFile.id)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.rag_enabled.is_(True),
            WorkspaceFile.is_latest.is_(True),
            WorkspaceFile.analysis_status == "completed",
            WorkspaceFile.deleted_at.is_(None),
        )
        .all()
    )