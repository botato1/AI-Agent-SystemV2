# backend/routers/workspace_router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.dependencies import (
    get_current_user_id,
    require_workspace_member,
    require_workspace_owner,
)
from backend.db.session import get_db
from backend.db.crud import auth_crud, room_crud, workspace_crud
from backend.schemas.workspace_schema import (
    WorkspaceCreateRequest,
    WorkspaceUpdateRequest,
    WorkspaceResponse,
    WorkspaceListResponse,
    WorkspaceMemberAddRequest,
    WorkspaceMemberRoleUpdateRequest,
    WorkspaceMemberResponse,
    WorkspaceMemberListResponse,
)


router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])


def _member_response(member, user) -> WorkspaceMemberResponse:
    return WorkspaceMemberResponse(
        id=member.id,
        user_id=member.user_id,
        username=user.username,
        display_name=user.display_name,
        role=member.role,
        joined_at=member.joined_at,
    )


# 워크스페이스 생성 (기본 카테고리 자동 생성 + 생성자를 owner로 등록)
@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace_api(
    request: WorkspaceCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    owner_id = UUID(current_user_id)

    workspace = workspace_crud.create_workspace(
        db, name=request.name, owner_id=owner_id, description=request.description,
    )
    room_crud.create_default_category(db, workspace_id=workspace.id, created_by=owner_id)
    workspace_crud.add_member(
        db, workspace_id=workspace.id, user_id=owner_id, added_by=owner_id, role="owner",
    )
    return WorkspaceResponse.model_validate(workspace)


# 내 워크스페이스 목록 조회
@router.get("", response_model=WorkspaceListResponse)
def get_workspace_list(
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    workspaces = workspace_crud.list_workspaces_for_user(db, UUID(current_user_id))
    return WorkspaceListResponse(
        workspaces=[WorkspaceResponse.model_validate(w) for w in workspaces]
    )


# 워크스페이스 단건 조회
@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace_api(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    workspace = require_workspace_member(db, workspace_id, current_user_id)
    return WorkspaceResponse.model_validate(workspace)


# 워크스페이스 정보 수정 (owner만)
@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace_api(
    workspace_id: UUID,
    request: WorkspaceUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_owner(db, workspace_id, current_user_id)

    fields = request.model_dump(exclude_unset=True)
    workspace = workspace_crud.update_workspace(db, workspace_id, **fields)
    return WorkspaceResponse.model_validate(workspace)


# 워크스페이스 삭제 (owner만, 소프트 삭제)
@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace_api(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_owner(db, workspace_id, current_user_id)
    workspace_crud.delete_workspace(db, workspace_id)


# 멤버 추가 (이메일로 검색, owner만)
@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_workspace_member_api(
    workspace_id: UUID,
    request: WorkspaceMemberAddRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_owner(db, workspace_id, current_user_id)

    user = auth_crud.get_user_by_email(db, request.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 이메일의 사용자를 찾을 수 없습니다.",
        )

    if workspace_crud.get_membership(db, workspace_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 워크스페이스에 속한 사용자입니다.",
        )

    member = workspace_crud.add_member(
        db, workspace_id=workspace_id, user_id=user.id,
        added_by=UUID(current_user_id), role=request.role,
    )
    return _member_response(member, user)


# 멤버 목록 조회
@router.get("/{workspace_id}/members", response_model=WorkspaceMemberListResponse)
def get_workspace_member_list(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    rows = workspace_crud.list_members(db, workspace_id)
    return WorkspaceMemberListResponse(
        members=[_member_response(member, user) for member, user in rows]
    )


# 멤버 역할 변경 (owner만, 마지막 owner 강등 방지)
@router.patch("/{workspace_id}/members/{user_id}", response_model=WorkspaceMemberResponse)
def update_workspace_member_role_api(
    workspace_id: UUID,
    user_id: UUID,
    request: WorkspaceMemberRoleUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_owner(db, workspace_id, current_user_id)

    membership = workspace_crud.get_membership(db, workspace_id, user_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스 멤버를 찾을 수 없습니다.",
        )

    if (
        membership.role == "owner"
        and request.role != "owner"
        and workspace_crud.count_owners(db, workspace_id) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="마지막 owner는 강등할 수 없습니다.",
        )

    member = workspace_crud.update_member_role(db, workspace_id, user_id, request.role)
    user = auth_crud.get_user_by_id(db, user_id)
    return _member_response(member, user)


# 멤버 제거 (owner만, 마지막 owner 제거 방지)
@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_workspace_member_api(
    workspace_id: UUID,
    user_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_owner(db, workspace_id, current_user_id)

    membership = workspace_crud.get_membership(db, workspace_id, user_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스 멤버를 찾을 수 없습니다.",
        )

    if membership.role == "owner" and workspace_crud.count_owners(db, workspace_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="마지막 owner는 제거할 수 없습니다.",
        )

    workspace_crud.remove_member(db, workspace_id, user_id)