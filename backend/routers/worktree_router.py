# backend/routers/worktree_router.py

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user_id, require_workspace_member
from backend.db.session import get_db
from backend.db.crud import file_crud, room_crud
from backend.services import document_service
from backend.schemas.worktree_schema import (
    WorktreeSchema,
    WorktreeListResponse,
    WorktreeFileResponse,
    WorktreeFileListResponse,
)


router = APIRouter(prefix="/api/workspaces/{workspace_id}/worktrees", tags=["Worktrees"])

# TODO: NAS 연결되면 이 경로/저장 로직을 NAS 저장으로 교체 (다른 업로드 로직과 동일한 임시 조치)
WORKTREE_STORAGE_DIR = Path("data/uploads/worktree_files")

CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".rb", ".php", ".swift", ".kt"}
CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".xml"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".md", ".txt"}


def _infer_file_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in CODE_EXTENSIONS:
        return "code"
    if suffix in CONFIG_EXTENSIONS:
        return "config"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    return "code"


def _save_worktree_file_to_local_storage(file_content: bytes, filename: str) -> tuple[str, str]:
    WORKTREE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}{Path(filename).suffix}"
    storage_path = WORKTREE_STORAGE_DIR / stored_filename
    storage_path.write_bytes(file_content)
    return str(storage_path), stored_filename


def _get_worktree_or_404(db: Session, worktree_id: uuid.UUID, workspace_id: uuid.UUID):
    worktree = file_crud.get_worktree(db, worktree_id)
    if not worktree or worktree.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="워크트리를 찾을 수 없습니다.",
        )
    return worktree


# 폴더 업로드 (워크트리 생성) — 파일 등록만, 코드 분석은 후속 작업
@router.post("", response_model=WorktreeSchema, status_code=status.HTTP_201_CREATED)
async def upload_worktree(
    workspace_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    root_folder_name: str = Form(..., min_length=1, max_length=255),
    files: list[UploadFile] = File(...),
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드할 파일이 없습니다.",
        )

    category = room_crud.get_default_category(db, workspace_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="워크스페이스의 기본 카테고리를 찾을 수 없습니다.",
        )

    worktree = file_crud.create_worktree(
        db,
        workspace_id=workspace_id,
        category_id=category.id,
        root_folder_name=root_folder_name,
        uploaded_by=uuid.UUID(current_user_id),
        total_file_count=len(files),
    )

    completed_count = 0
    failed_count = 0
    analyzable_file_ids: list[uuid.UUID] = []

    for f in files:
        try:
            file_content = await f.read()
            storage_path, stored_filename = _save_worktree_file_to_local_storage(file_content, f.filename)
            file_kind = _infer_file_kind(f.filename)

            workspace_file = file_crud.create_workspace_file(
                db,
                workspace_id=workspace_id,
                category_id=category.id,
                worktree_id=worktree.id,
                uploaded_by=uuid.UUID(current_user_id),
                original_filename=Path(f.filename).name,
                relative_path=f.filename,
                stored_filename=stored_filename,
                storage_path=storage_path,
                mime_type=f.content_type,
                extension=Path(f.filename).suffix.lstrip("."),
                file_kind=file_kind,
                origin_type="worktree",
                file_size_bytes=len(file_content),
                sha256_hash=hashlib.sha256(file_content).hexdigest(),
                version_group_id=uuid.uuid4(),
                analysis_status="pending",
            )
            completed_count += 1

            if file_kind in ("document", "image"):
                analyzable_file_ids.append(workspace_file.id)

        except Exception as e:
            db.rollback()
            failed_count += 1
            print(f"[worktree_router] 파일 저장 실패: {f.filename} / {repr(e)}")

    if completed_count == 0:
        final_status = "failed"  # 업로드 자체가 전부 실패 - 분석할 파일도 없음
    elif analyzable_file_ids:
        final_status = "processing"  # 문서/이미지 분석이 아직 안 끝났으므로 완료 아님
    elif failed_count == 0:
        final_status = "completed"
    else:
        final_status = "partially_completed"

    worktree = file_crud.update_worktree_counts(
        db, worktree.id,
        completed_file_count=completed_count,
        failed_file_count=failed_count,
        status=final_status,
    )

    # 문서/이미지 파일만 백그라운드로 분석 (코드/설정 파일 분석 로직은 아직 없음)
    for file_id in analyzable_file_ids:
        background_tasks.add_task(document_service.analyze_worktree_file_background, file_id)

    return WorktreeSchema.model_validate(worktree)


# 워크트리 목록 조회
@router.get("", response_model=WorktreeListResponse)
def get_worktree_list(
    workspace_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    worktrees = file_crud.list_worktrees(db, workspace_id)
    return WorktreeListResponse(worktrees=[WorktreeSchema.model_validate(w) for w in worktrees])


# 워크트리 단건 조회
@router.get("/{worktree_id}", response_model=WorktreeSchema)
def get_worktree_api(
    workspace_id: uuid.UUID,
    worktree_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    worktree = _get_worktree_or_404(db, worktree_id, workspace_id)
    return WorktreeSchema.model_validate(worktree)


# 워크트리 내 파일목록 조회
@router.get("/{worktree_id}/files", response_model=WorktreeFileListResponse)
def get_worktree_files(
    workspace_id: uuid.UUID,
    worktree_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_worktree_or_404(db, worktree_id, workspace_id)

    files = file_crud.list_files_by_worktree(db, worktree_id)
    return WorktreeFileListResponse(
        files=[WorktreeFileResponse.model_validate(f) for f in files]
    )

# 워크트리 삭제 (내부 파일 전체 정리 후 워크트리 자체 삭제)
@router.delete("/{worktree_id}")
def delete_worktree_api(
    workspace_id: uuid.UUID,
    worktree_id: uuid.UUID,
    current_user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    require_workspace_member(db, workspace_id, current_user_id)
    _get_worktree_or_404(db, worktree_id, workspace_id)

    files = file_crud.list_files_by_worktree(db, worktree_id)
    deleted_count = 0
    failed_count = 0

    for f in files:
        try:
            result = document_service.delete_processed_document(db, f.id)
            if result.get("status") == "success":
                deleted_count += 1
            else:
                failed_count += 1
                print(f"[worktree_router] 워크트리 파일 삭제 실패: file_id={f.id} / {result.get('error')}")
        except Exception as e:
            db.rollback()
            failed_count += 1
            print(f"[worktree_router] 워크트리 파일 삭제 중 예외: file_id={f.id} / {repr(e)}")

    file_crud.delete_worktree(db, worktree_id)

    return {
        "status": "success",
        "worktree_id": str(worktree_id),
        "deleted_file_count": deleted_count,
        "failed_file_count": failed_count,
        "message": "워크트리가 삭제되었습니다.",
    }