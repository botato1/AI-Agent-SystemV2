# 문서 관련 API 엔드포인트
from typing import Literal

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status

from backend.services.document_service import (
    upload_and_process_document,
    delete_processed_document,
    get_document_detail,
)
from backend.db.crud import get_documents_for_user
from backend.core.dependencies import get_current_user_id


router = APIRouter(
    prefix="/api/documents",
    tags=["Documents"]
)


# 업로드된 전체 문서 목록 조회 API
# 실제 경로: GET /api/documents
@router.get("")
def get_document_list(
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        rows = get_documents_for_user(current_user_id)

        documents = [
            {
                "document_id": row["document_id"],
                "filename": row["filename"],
                "room_id": row.get("room_id"),  # TODO: v1 호환용, 추후 제거 예정
                "conversation_id": row.get("conversation_id") or row.get("room_id"),
                "type": row.get("type"),
                "source": row.get("source"),
                "json_path": row.get("json_path"),
                "chroma_status": row.get("chroma_status"),
                "created_at": row["created_at"],
            }
            for row in rows
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
# 실제 경로: POST /api/documents/upload
# 프론트는 이 API만 호출
# 문서 파일은 8003 문서 처리 서버로 전달한다.
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    room_id: str | None = Form(None),  # TODO: v1 호환용, 추후 제거 예정
    document_type: Literal["document", "meeting"] = Form("document", alias="type"),
    current_user_id: str = Depends(get_current_user_id),
):
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드할 파일이 없습니다.",
        )

    try:
        return await upload_and_process_document(
            file=file,
            conversation_id=conversation_id,
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


# 문서 상세 조회 API
# 실제 경로: GET /api/documents/{document_id}
# 문서 보관함에서 문서 1개 클릭 시 사용
@router.get("/{document_id}")
def get_document_detail_api(
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        result = get_document_detail(
            document_id=document_id,
            user_id=current_user_id,
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="문서를 찾을 수 없습니다.",
            )

        return result

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


# 문서 삭제 API
# 실제 경로: DELETE /api/documents/{document_id}
@router.delete("/{document_id}")
def delete_document_api(
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        result = delete_processed_document(
            document_id=document_id,
            user_id=current_user_id,
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="삭제할 문서를 찾을 수 없습니다.",
            )

        return result

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