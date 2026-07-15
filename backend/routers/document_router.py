# backend/routers/document_router.py

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.services.document_service import (
    upload_and_process_document,
    delete_processed_document,
    get_document_detail,
)
from backend.db.crud import file_crud
from backend.db.session import get_db
from backend.core.dependencies import get_current_user_id, require_workspace_member


router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/documents",
    tags=["Documents"],
)


def _get_workspace_file_or_404(db: Session, file_id: UUID, workspace_id: UUID):
    workspace_file = file_crud.get_file(db, file_id)
    if not workspace_file or workspace_file.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="문서를 찾을 수 없습니다.",
        )
    return workspace_file


# 워크스페이스 내 문서 목록 조회
@router.get("")
def get_document_list(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    try:
        files = file_crud.list_files_by_kind(db, workspace_id, "document")

        documents = [
            {
                "document_id": str(f.id),
                "filename": f.original_filename,
                "analysis_status": f.analysis_status,
                "created_at": f.created_at,
            }
            for f in files
        ]

        return {
            "status": "success",
            "documents": documents,
            "error": None,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[document_router] 문서 목록 조회 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="문서 목록 조회 중 오류가 발생했습니다.",
        )


# 문서 업로드 통합 API
# 문서 파일은 8003 문서 처리 서버로 전달한다.
@router.post("/upload")
async def upload_document(
    workspace_id: UUID,
    file: UploadFile = File(...),
    room_id: str | None = Form(None),
    document_type: Literal["document", "meeting"] = Form("document", alias="type"),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드할 파일이 없습니다.",
        )

    try:
        return await upload_and_process_document(
            db=db,
            file=file,
            workspace_id=workspace_id,
            room_id=room_id,
            document_type=document_type,
            user_id=current_user_id,
        )

    except HTTPException:
        raise
    except ValueError as e:
        print(f"[document_router] 문서 업로드 요청 값 오류: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="문서 업로드 요청 값이 올바르지 않습니다.",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방 또는 문서를 찾을 수 없습니다.",
        )
    except Exception as e:
        print(f"[document_router] 문서 업로드 처리 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="문서 업로드 처리 중 오류가 발생했습니다.",
        )


# 문서 상세 조회
@router.get("/{document_id}")
def get_document_detail_api(
    workspace_id: UUID,
    document_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_workspace_file_or_404(db, document_id, workspace_id)

    try:
        return get_document_detail(db=db, file_id=document_id)

    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="문서를 찾을 수 없습니다.",
        )
    except Exception as e:
        print(f"[document_router] 문서 상세 조회 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="문서 상세 조회 중 오류가 발생했습니다.",
        )


# 문서 삭제
@router.delete("/{document_id}")
def delete_document_api(
    workspace_id: UUID,
    document_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_workspace_file_or_404(db, document_id, workspace_id)

    try:
        return delete_processed_document(db=db, file_id=document_id)

    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="삭제할 문서를 찾을 수 없습니다.",
        )
    except Exception as e:
        print(f"[document_router] 문서 삭제 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="문서 삭제 중 오류가 발생했습니다.",
        )