"""워크스페이스/멤버 CRUD (가동현 파트 — 기본 템플릿)

주의: 워크스페이스 생성 시 서비스 계층에서 categories에
is_default=true 카테고리를 자동 생성해줘야 함 (room_crud.create_default_category 참고).
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import Workspace, WorkspaceMember


def create_workspace(db: Session, name: str, owner_id: uuid.UUID, **fields) -> Workspace:
    row = Workspace(name=name, owner_id=owner_id, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_workspace(db: Session, workspace_id: uuid.UUID) -> Optional[Workspace]:
    return (
        db.query(Workspace)
        .filter(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
        .first()
    )


def list_workspaces_for_user(db: Session, user_id: uuid.UUID) -> list[Workspace]:
    return (
        db.query(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(WorkspaceMember.user_id == user_id, WorkspaceMember.removed_at.is_(None))
        .all()
    )


def add_member(
    db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, added_by: uuid.UUID, role: str = "member"
) -> WorkspaceMember:
    row = WorkspaceMember(
        workspace_id=workspace_id, user_id=user_id, added_by=added_by, role=role
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
