# backend/routers/category_router.py

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import room_crud
from backend.schemas.workspace_schema import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CategoryResponse,
    CategoryListResponse,
)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/categories", tags=["Categories"])
item_router = APIRouter(prefix="/api/categories", tags=["Categories"])


@router.get("", response_model=CategoryListResponse)
def list_categories_api(
    workspace_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    items = room_crud.list_categories(db, workspace_id)
    return CategoryListResponse(categories=[CategoryResponse.model_validate(i) for i in items])


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category_api(
    workspace_id: uuid.UUID,
    request: CategoryCreateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    item = room_crud.create_category(
        db, workspace_id=workspace_id, name=request.name, created_by=uuid.UUID(current_user_id),
    )
    return CategoryResponse.model_validate(item)


def _get_category_or_404(db: Session, category_id: uuid.UUID):
    category = room_crud.get_category(db, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="카테고리를 찾을 수 없습니다.",
        )
    return category


@item_router.patch("/{category_id}", response_model=CategoryResponse)
def update_category_api(
    category_id: uuid.UUID,
    request: CategoryUpdateRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    category = _get_category_or_404(db, category_id)
    require_workspace_member(db, category.workspace_id, current_user_id)

    update_fields = request.model_dump(exclude_unset=True)
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 내용이 없습니다.",
        )

    item = room_crud.update_category(db, category_id, **update_fields)
    return CategoryResponse.model_validate(item)


@item_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category_api(
    category_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    category = _get_category_or_404(db, category_id)
    require_workspace_member(db, category.workspace_id, current_user_id)

    if category.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="기본 카테고리는 삭제할 수 없습니다.",
        )

    room_crud.delete_category(db, category_id)