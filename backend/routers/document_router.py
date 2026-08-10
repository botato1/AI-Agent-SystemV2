# backend/routers/document_router.py

from typing import Literal
from uuid import UUID
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.core.security import create_document_ws_ticket
from backend.services.document_service import (
    upload_and_process_document,
    delete_processed_document,
    get_document_detail,
    retry_document_analysis,
)
from backend.db.crud import document_crud, file_crud, similarity_crud
from backend.schemas.document_schema import DocumentFigureListResponse, DocumentGraphResponse
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

# 문서 유사도 그래프뷰 조회
@router.get("/graph", response_model=DocumentGraphResponse)
def get_document_graph_api(
    workspace_id: UUID,
    min_score: float = Query(default=0.6, ge=0, le=1),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    nodes = file_crud.list_graph_eligible_files(db, workspace_id)
    edges = similarity_crud.get_similarities_for_workspace(db, workspace_id, min_score=min_score)

    return DocumentGraphResponse(
        nodes=[{"file_id": f.id, "filename": f.original_filename} for f in nodes],
        edges=[
            {
                "source_file_id": e.source_file_id,
                "target_file_id": e.target_file_id,
                "similarity_score": e.similarity_score,
            }
            for e in edges
        ],
    )


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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    room_id: str | None = Form(None),
    meeting_id: str | None = Form(None),
    document_type: Literal["document", "meeting"] = Form("document", alias="type"),
    previous_file_id: UUID | None = Form(None),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(
        db,
        workspace_id,
        current_user_id,
    )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드할 파일이 없습니다.",
        )

    if previous_file_id is not None:
        previous_file = _get_workspace_file_or_404(
            db,
            previous_file_id,
            workspace_id,
        )

        if previous_file.file_kind != "document":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="문서 파일만 이전 버전으로 지정할 수 있습니다.",
            )

    try:
        return await upload_and_process_document(
            db=db,
            file=file,
            workspace_id=workspace_id,
            background_tasks=background_tasks,
            room_id=room_id,
            meeting_id=meeting_id,
            document_type=document_type,
            current_user_id=current_user_id,
            previous_file_id=previous_file_id,
        )

    except HTTPException:
        raise

    except file_crud.FileVersionError as e:
        print(f"[document_router] 문서 업로드 요청 값 오류: {e!r}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방 또는 문서를 찾을 수 없습니다.",
        )

    except Exception as e:
        print(f"[document_router] 문서 업로드 처리 실패: {e!r}")
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

# 문서 재분석 요청
@router.post("/{document_id}/retry")
async def retry_document_api(
    workspace_id: UUID,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_workspace_file_or_404(db, document_id, workspace_id)

    try:
        return await retry_document_analysis(db=db, file_id=document_id, background_tasks=background_tasks)
    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="재분석할 문서를 찾을 수 없습니다.",
        )
    except Exception as e:
        print(f"[document_router] 문서 재분석 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="문서 재분석 중 오류가 발생했습니다.",
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
    
    
@router.get("/{document_id}/figures", response_model=DocumentFigureListResponse)
def get_document_figures_api(
    workspace_id: UUID,
    document_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_workspace_file_or_404(db, document_id, workspace_id)

    figures = document_crud.list_figures_by_file(db, document_id)
    return DocumentFigureListResponse(
        figures=[
            {"figure_id": f.id, "page_number": f.page_number, "type": f.figure_type, "image_url": f.image_url}
            for f in figures
        ]
    )

# 원본 파일 다운로드/스트리밍
@router.get("/{document_id}/file")
def get_document_file_api(
    workspace_id: UUID,
    document_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    workspace_file = _get_workspace_file_or_404(db, document_id, workspace_id)

    file_path = Path(workspace_file.storage_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="원본 파일을 찾을 수 없습니다.",
        )

    return FileResponse(
        path=file_path,
        media_type=workspace_file.mime_type or "application/octet-stream",
        filename=workspace_file.original_filename,
    )

class DocumentWsTicketResponse(BaseModel):
    ws_ticket: str


# 문서/그래프 실시간 연결용 WS 티켓 발급
@router.get("/stream/ticket", response_model=DocumentWsTicketResponse)
def get_document_ws_ticket(
    workspace_id: UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    ticket = create_document_ws_ticket(current_user_id, str(workspace_id))
    return DocumentWsTicketResponse(ws_ticket=ticket)