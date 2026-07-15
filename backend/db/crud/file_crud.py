"""워크트리/파일 CRUD (정승현 파트 — 기본 템플릿)"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import RoomFileLink, Worktree, WorkspaceFile


def create_worktree(db: Session, workspace_id: uuid.UUID, root_folder_name: str, uploaded_by: uuid.UUID, total_file_count: int) -> Worktree:
    row = Worktree(
        workspace_id=workspace_id,
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
