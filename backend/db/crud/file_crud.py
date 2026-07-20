"""워크트리/파일 CRUD (정승현 파트 — 기본 템플릿)"""

import uuid
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.db.modules import RoomFileLink, Worktree, WorkspaceFile


def create_worktree(db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, root_folder_name: str, uploaded_by: uuid.UUID, total_file_count: int) -> Worktree:
    row = Worktree(
        workspace_id=workspace_id,
        category_id=category_id,
        root_folder_name=root_folder_name,
        uploaded_by=uploaded_by,
        total_file_count=total_file_count,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_workspace_file(db: Session, **fields) -> WorkspaceFile:
    """file_kind로 document/code/config/image/audio 판별 후 호출."""
    row = WorkspaceFile(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_file(db: Session, file_id: uuid.UUID) -> Optional[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.id == file_id, WorkspaceFile.deleted_at.is_(None))
        .first()
    )


def list_files_by_kind(db: Session, workspace_id: uuid.UUID, file_kind: str) -> list[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.file_kind == file_kind,
            WorkspaceFile.is_latest.is_(True),
            WorkspaceFile.deleted_at.is_(None),
        )
        .all()
    )


def link_file_to_room(db: Session, room_id: uuid.UUID, file_id: uuid.UUID, linked_by: uuid.UUID) -> RoomFileLink:
    row = RoomFileLink(room_id=room_id, file_id=file_id, linked_by=linked_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_analysis_status(db: Session, file_id: uuid.UUID, status: str, error: Optional[str] = None) -> Optional[WorkspaceFile]:
    row = get_file(db, file_id)
    if row:
        row.analysis_status = status
        row.processing_error = error
        db.commit()
        db.refresh(row)
    return row

def list_files(db: Session, workspace_id: uuid.UUID) -> list[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.is_latest.is_(True),
            WorkspaceFile.deleted_at.is_(None),
        )
        .all()
    )


def delete_file(db: Session, file_id: uuid.UUID) -> Optional[WorkspaceFile]:
    row = get_file(db, file_id)
    if row:
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


def list_files_by_room(db: Session, room_id: uuid.UUID) -> list[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .join(RoomFileLink, RoomFileLink.file_id == WorkspaceFile.id)
        .filter(
            RoomFileLink.room_id == room_id,
            WorkspaceFile.deleted_at.is_(None),
        )
        .all()
    )

# room_file_links는 deleted_at이 없는 순수 연결 테이블이라 실제 row를 삭제
def unlink_file_from_room(db: Session, room_id: uuid.UUID, file_id: uuid.UUID) -> bool:
    row = (
        db.query(RoomFileLink)
        .filter(RoomFileLink.room_id == room_id, RoomFileLink.file_id == file_id)
        .first()
    )
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True

def increment_retry_count(db: Session, file_id: uuid.UUID) -> Optional[WorkspaceFile]:
    row = get_file(db, file_id)
    if row:
        row.retry_count += 1
        row.last_attempt_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row

def get_worktree(db: Session, worktree_id: uuid.UUID) -> Optional[Worktree]:
    return db.query(Worktree).filter(Worktree.id == worktree_id).first()


def list_worktrees(db: Session, workspace_id: uuid.UUID) -> list[Worktree]:
    return (
        db.query(Worktree)
        .filter(Worktree.workspace_id == workspace_id)
        .order_by(Worktree.created_at.desc())
        .all()
    )


def update_worktree_counts(db: Session, worktree_id: uuid.UUID, **fields) -> Optional[Worktree]:
    row = get_worktree(db, worktree_id)
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        if fields.get("status") in ("completed", "partially_completed", "failed"):
            row.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


def list_files_by_worktree(db: Session, worktree_id: uuid.UUID) -> list[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.worktree_id == worktree_id, WorkspaceFile.deleted_at.is_(None))
        .order_by(WorkspaceFile.relative_path)
        .all()
    )