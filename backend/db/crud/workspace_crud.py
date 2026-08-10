"""워크스페이스/멤버 CRUD (가동현 파트 — 기본 템플릿)

주의: 워크스페이스 생성 시 서비스 계층에서 categories에
is_default=true 카테고리를 자동 생성해줘야 함 (room_crud.create_default_category 참고).
"""

import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.modules import User, Workspace, WorkspaceMember


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
        .filter(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.removed_at.is_(None),
            Workspace.deleted_at.is_(None),
        )
        .all()
    )


def update_workspace(db: Session, workspace_id: uuid.UUID, **fields) -> Optional[Workspace]:
    row = get_workspace(db, workspace_id)
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
    return row


def delete_workspace(db: Session, workspace_id: uuid.UUID) -> Optional[Workspace]:
    row = get_workspace(db, workspace_id)
    if row:
        row.deleted_at = func.now()
        db.commit()
        db.refresh(row)
    return row


def add_member(
    db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, added_by: uuid.UUID, role: str = "member"
) -> WorkspaceMember:
    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if existing:
        # 예전에 제거됐던 멤버를 다시 추가하는 경우 - 새로 INSERT하면 유니크 제약 위반되므로
        # 기존 row를 되살린다
        existing.removed_at = None
        existing.role = role
        existing.added_by = added_by
        existing.joined_at = func.now()
        db.commit()
        db.refresh(existing)
        return existing

    row = WorkspaceMember(
        workspace_id=workspace_id, user_id=user_id, added_by=added_by, role=role
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

# workspace_id + user_id 조합으로 이 사용자가 이 워크스페이스의 멤버인지를 조회하는 함수
def get_membership(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Optional[WorkspaceMember]:
    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.removed_at.is_(None),
        )
        .first()
    )


def list_members(db: Session, workspace_id: uuid.UUID) -> list[tuple[WorkspaceMember, User]]:
    """(WorkspaceMember, User) 튜플 목록. User를 join해서 username/display_name을 같이 가져온다."""
    return (
        db.query(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.removed_at.is_(None))
        .all()
    )


def count_owners(db: Session, workspace_id: uuid.UUID) -> int:
    """마지막 owner 강등/제거 방지 체크용."""
    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "owner",
            WorkspaceMember.removed_at.is_(None),
        )
        .count()
    )


def update_member_role(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID, role: str) -> Optional[WorkspaceMember]:
    row = get_membership(db, workspace_id, user_id)
    if row:
        row.role = role
        db.commit()
        db.refresh(row)
    return row


def remove_member(db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Optional[WorkspaceMember]:
    row = get_membership(db, workspace_id, user_id)
    if row:
        row.removed_at = func.now()
        db.commit()
        db.refresh(row)
    return row