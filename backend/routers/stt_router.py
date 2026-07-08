# backend/routers/stt_router.py
# STT 관련 API 엔드포인트
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status

from backend.core.dependencies import get_current_user_id
from backend.services.stt_upload_service import (
    upload_and_process_stt,
    get_stt_list,
    get_stt_detail,
    delete_stt_document,
)


router = APIRouter(
    prefix="/api/stt",
    tags=["STT"]
)


# STT 업로드 API
@router.post("/upload")
async def upload_stt_file(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    room_id: str | None = Form(None),  # TODO: v1 호환용, 추후 제거 예정
    current_user_id: str = Depends(get_current_user_id),
):
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드할 음성 파일이 없습니다.",
        )

    try:
        return await upload_and_process_stt(
            file=file,
            conversation_id=conversation_id,
            room_id=room_id,
            user_id=current_user_id,
        )

    except HTTPException:
        raise
    except ValueError as e:
        print(f"[stt_router] 음성 업로드 요청 값 오류: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="음성 업로드 요청 값이 올바르지 않습니다.",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅방 또는 음성 문서를 찾을 수 없습니다.",
        )
    except Exception as e:
        print(f"[stt_router] 음성 업로드 처리 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="음성 업로드 처리 중 오류가 발생했습니다.",
        )


# STT 음성 목록 조회 API
@router.get("/list")
def get_stt_file_list(
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        return get_stt_list(
            user_id=current_user_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[stt_router] 음성 목록 조회 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="음성 목록 조회 중 오류가 발생했습니다.",
        )


# STT 음성 상세 조회 API
@router.get("/{document_id}")
def get_stt_file_detail(
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        result = get_stt_detail(
            document_id=document_id,
            user_id=current_user_id,
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="음성 문서를 찾을 수 없습니다.",
            )

        return result

    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="음성 문서를 찾을 수 없습니다.",
        )
    except Exception as e:
        print(f"[stt_router] 음성 상세 조회 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="음성 상세 조회 중 오류가 발생했습니다.",
        )


# STT 음성 삭제 API
@router.delete("/{document_id}")
async def delete_stt_file(
    document_id: str,
    current_user_id: str = Depends(get_current_user_id),
):
    try:
        result = await delete_stt_document(
            document_id=document_id,
            user_id=current_user_id,
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="삭제할 음성 문서를 찾을 수 없습니다.",
            )

        return result

    except HTTPException:
        raise
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="삭제할 음성 문서를 찾을 수 없습니다.",
        )
    except Exception as e:
        print(f"[stt_router] 음성 삭제 실패: {repr(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="음성 삭제 중 오류가 발생했습니다.",
        )