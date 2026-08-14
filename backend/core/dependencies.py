# backend/core/dependencies.py

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.crud import workspace_crud
from backend.core.security import get_user_id_from_access_token

security = HTTPBearer()


def get_access_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    return credentials.credentials


def get_current_user_id(access_token: str = Depends(get_access_token)) -> str:
    try:
        return get_user_id_from_access_token(access_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Access Token입니다.",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 정보를 확인할 수 없습니다.",
        )
    
def require_workspace_member(db: Session, workspace_id: UUID, user_id: str):
    workspace = workspace_crud.get_workspace(db, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크스페이스를 찾을 수 없습니다.",
        )

    membership = workspace_crud.get_membership(db, workspace_id, UUID(user_id))
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="워크스페이스 접근 권한이 없습니다.",
        )

    return workspace

def require_workspace_owner(db: Session, workspace_id: UUID, user_id: str):
    workspace = require_workspace_member(db, workspace_id, user_id)

    membership = workspace_crud.get_membership(db, workspace_id, UUID(user_id))
    if membership.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="워크스페이스 owner만 수행할 수 있는 작업입니다.",
        )

    return workspace

def resolve_category(db: Session, workspace_id: UUID, category_id: UUID | None):
    from backend.db.crud import room_crud

    if category_id is None:
        category = room_crud.get_default_category(db, workspace_id)
    else:
        category = room_crud.get_category(db, category_id)
        if not category or category.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="워크스페이스에 속하지 않는 카테고리입니다.",
            )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="워크스페이스의 기본 카테고리를 찾을 수 없습니다.",
        )
    return category
