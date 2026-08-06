# backend/db/crud/file_crud.py

"""워크트리/파일 CRUD (정승현 파트 — 기본 템플릿)"""

import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import text

from sqlalchemy.orm import Session

from backend.db.modules import RoomFileLink, Worktree, WorkspaceFile, Meeting

class FileVersionError(ValueError):
    """파일 버전 연결 요청이 유효하지 않을 때 발생한다."""

def create_worktree(db: Session, workspace_id: uuid.UUID, category_id: uuid.UUID, root_folder_name: str, uploaded_by: uuid.UUID, total_file_count: int) -> Worktree:
    row = Worktree(
        workspace_id=workspace_id,
        category_id=category_id,
        root_folder_name=root_folder_name,
        uploaded_by=uploaded_by,
        total_file_count=total_file_count,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_workspace_file(db: Session, **fields) -> WorkspaceFile:
    """file_kind로 document/code/config/image/audio 판별 후 호출."""
    row = WorkspaceFile(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def create_versioned_workspace_file(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    original_filename: str,
    previous_file_id: uuid.UUID | None = None,
    **fields,
) -> WorkspaceFile:
    """
    새 파일 또는 기존 파일의 다음 버전을 생성한다.

    previous_file_id가 없으면 새로운 버전 그룹을 생성한다.
    previous_file_id가 있으면 해당 파일이 속한 버전 그룹의
    현재 최신 버전을 기준으로 다음 버전을 생성한다.

    기존 최신 버전 해제와 새 버전 생성은 하나의 트랜잭션으로 처리한다.
    """

    try:
        if previous_file_id is None:
            # 새 파일이므로 새로운 버전 그룹을 시작한다.
            version_group_id = uuid.uuid4()
            version_no = 1
            actual_previous_version_id = None

        else:
            # 전달받은 파일이 실제로 같은 워크스페이스에 존재하는지 확인한다.
            previous_file = (
                db.query(WorkspaceFile)
                .filter(
                    WorkspaceFile.id == previous_file_id,
                    WorkspaceFile.workspace_id == workspace_id,
                    WorkspaceFile.deleted_at.is_(None),
                )
                .first()
            )

            if not previous_file:
                raise FileVersionError(
                    "이전 버전 파일을 찾을 수 없거나 "
                    "현재 워크스페이스에 속하지 않습니다."
                )

            expected_category_id = fields.get("category_id")
            expected_file_kind = fields.get("file_kind")

            if (
                expected_category_id is not None
                and previous_file.category_id != expected_category_id
            ):
                raise FileVersionError(
                    "이전 버전 파일과 새 파일의 카테고리가 다릅니다."
                )

            if (
                expected_file_kind is not None
                and previous_file.file_kind != expected_file_kind
            ):
                raise FileVersionError(
                    "이전 버전 파일과 새 파일의 파일 종류가 다릅니다."
                )

            # 같은 버전 그룹에 대한 동시 업로드를 직렬화한다.
            lock_key = (
                f"workspace_file_version:"
                f"{workspace_id}:"
                f"{previous_file.version_group_id}"
            )

            db.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtextextended(:lock_key, 0)"
                    ")"
                ),
                {"lock_key": lock_key},
            )

            # 사용자가 이전 버전 ID를 전달했더라도,
            # 실제 생성 기준은 해당 그룹의 현재 최신 버전으로 한다.
            latest_version = (
                db.query(WorkspaceFile)
                .filter(
                    WorkspaceFile.workspace_id == workspace_id,
                    WorkspaceFile.version_group_id
                    == previous_file.version_group_id,
                    WorkspaceFile.is_latest.is_(True),
                    WorkspaceFile.deleted_at.is_(None),
                )
                .order_by(WorkspaceFile.version_no.desc())
                .with_for_update()
                .first()
            )

            if not latest_version:
                raise FileVersionError(
                    "해당 버전 그룹의 최신 파일을 찾을 수 없습니다."
                )

            latest_version.is_latest = False

            version_group_id = latest_version.version_group_id
            version_no = latest_version.version_no + 1
            actual_previous_version_id = latest_version.id

            # 변경 사항을 반영하지만 아직 commit하지 않는다.
            db.flush()

        row_fields = dict(fields)
        row_fields.update(
            {
                "workspace_id": workspace_id,
                "original_filename": original_filename,
                "version_group_id": version_group_id,
                "version_no": version_no,
                "previous_version_id": actual_previous_version_id,
                "is_latest": True,
            }
        )

        row = WorkspaceFile(**row_fields)

        db.add(row)
        db.commit()
        db.refresh(row)

        return row

    except Exception:
        db.rollback()
        raise


def get_file(db: Session, file_id: uuid.UUID) -> Optional[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.id == file_id, WorkspaceFile.deleted_at.is_(None))
        .first()
    )


def list_files_by_kind(db: Session, workspace_id: uuid.UUID, file_kind: str) -> list[WorkspaceFile]:
    """일반 문서 목록 조회용. 워크트리(코드 폴더) 업로드 파일, 회의 요약 문서, 회의록 내보내기 PDF는
    각각 워크트리/회의 화면에서만 보여야 하므로 제외한다."""
    return (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.file_kind == file_kind,
            WorkspaceFile.origin_type.notin_(["worktree", "meeting_summary", "meeting_export"]),
            WorkspaceFile.is_latest.is_(True),
            WorkspaceFile.deleted_at.is_(None),
        )
        .all()
    )

def list_graph_eligible_files(
    db: Session, workspace_id: uuid.UUID, exclude_file_id: Optional[uuid.UUID] = None
) -> list[WorkspaceFile]:
    """그래프뷰 대상 문서 조회. file_kind=document, analysis_status=completed, is_latest=true."""
    q = db.query(WorkspaceFile).filter(
        WorkspaceFile.workspace_id == workspace_id,
        WorkspaceFile.file_kind == "document",
        WorkspaceFile.origin_type.notin_(["meeting_summary", "meeting_export"]),
        WorkspaceFile.analysis_status == "completed",
        WorkspaceFile.is_latest.is_(True),
        WorkspaceFile.deleted_at.is_(None),
    )
    if exclude_file_id:
        q = q.filter(WorkspaceFile.id != exclude_file_id)
    return q.all()

def link_file_to_room(db: Session, room_id: uuid.UUID, file_id: uuid.UUID, linked_by: uuid.UUID) -> RoomFileLink:
    row = RoomFileLink(room_id=room_id, file_id=file_id, linked_by=linked_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_analysis_status(db: Session, file_id: uuid.UUID, status: str, error: Optional[str] = None) -> Optional[WorkspaceFile]:
    row = get_file(db, file_id)
    if row:
        row.analysis_status = status
        row.processing_error = error
        db.commit()
        db.refresh(row)
    return row

def list_files(db: Session, workspace_id: uuid.UUID) -> list[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.is_latest.is_(True),
            WorkspaceFile.deleted_at.is_(None),
        )
        .all()
    )


def delete_file(db: Session, file_id: uuid.UUID) -> Optional[WorkspaceFile]:
    row = get_file(db, file_id)
    if row:
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


def list_files_by_room(db: Session, room_id: uuid.UUID) -> list[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .join(RoomFileLink, RoomFileLink.file_id == WorkspaceFile.id)
        .filter(
            RoomFileLink.room_id == room_id,
            WorkspaceFile.deleted_at.is_(None),
        )
        .all()
    )

# room_file_links는 deleted_at이 없는 순수 연결 테이블이라 실제 row를 삭제
def unlink_file_from_room(db: Session, room_id: uuid.UUID, file_id: uuid.UUID) -> bool:
    row = (
        db.query(RoomFileLink)
        .filter(RoomFileLink.room_id == room_id, RoomFileLink.file_id == file_id)
        .first()
    )
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True

def increment_retry_count(db: Session, file_id: uuid.UUID) -> Optional[WorkspaceFile]:
    row = get_file(db, file_id)
    if row:
        row.retry_count += 1
        row.last_attempt_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row

def get_worktree(db: Session, worktree_id: uuid.UUID) -> Optional[Worktree]:
    return db.query(Worktree).filter(Worktree.id == worktree_id).first()


def list_worktrees(db: Session, workspace_id: uuid.UUID) -> list[Worktree]:
    return (
        db.query(Worktree)
        .filter(Worktree.workspace_id == workspace_id)
        .order_by(Worktree.created_at.desc())
        .all()
    )


def update_worktree_counts(db: Session, worktree_id: uuid.UUID, **fields) -> Optional[Worktree]:
    row = get_worktree(db, worktree_id)
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        if fields.get("status") in ("completed", "partially_completed", "failed"):
            row.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row

def finalize_worktree_status_if_analysis_done(db: Session, worktree_id: uuid.UUID) -> Optional[Worktree]:
    """분석 대상 파일(document/image)이 전부 completed/failed로 settle되면
    워크트리 status를 최종값으로 전이한다. status가 이미 processing이 아니면
    (분석 대상이 없었거나 이미 최종 상태) 아무 것도 안 한다."""
    worktree = get_worktree(db, worktree_id)
    if not worktree or worktree.status != "processing":
        return worktree

    analyzable = [
        f for f in list_files_by_worktree(db, worktree_id)
        if f.file_kind in ("document", "image")
    ]
    unsettled = [f for f in analyzable if f.analysis_status not in ("completed", "failed")]
    if unsettled:
        return worktree  # 아직 분석 중인 파일이 남아있음

    analysis_failed_count = sum(1 for f in analyzable if f.analysis_status == "failed")

    if analysis_failed_count == 0 and worktree.failed_file_count == 0:
        new_status = "completed"
    elif worktree.completed_file_count == 0 and analysis_failed_count == len(analyzable):
        new_status = "failed"
    else:
        new_status = "partially_completed"

    return update_worktree_counts(db, worktree_id, status=new_status)

def list_files_by_worktree(db: Session, worktree_id: uuid.UUID) -> list[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.worktree_id == worktree_id, WorkspaceFile.deleted_at.is_(None))
        .order_by(WorkspaceFile.relative_path)
        .all()
    )

def delete_worktree(db: Session, worktree_id: uuid.UUID) -> None:
    """Worktree는 deleted_at 컬럼이 없어 소프트 삭제 대상이 아니므로 하드 삭제한다.
    소프트 삭제된 workspace_files는 행 자체가 남아있어 worktree_id FK가 여전히
    걸려있으므로, 하드 삭제 전에 그 파일들의 worktree_id를 먼저 NULL로 해제한다."""
    db.query(WorkspaceFile).filter(WorkspaceFile.worktree_id == worktree_id).update(
        {"worktree_id": None}, synchronize_session=False
    )
    worktree = get_worktree(db, worktree_id)
    if worktree:
        db.delete(worktree)
        db.commit()

def create_meeting_export(
    db: Session, *, workspace_id: uuid.UUID, category_id: uuid.UUID, meeting_id: uuid.UUID,
    uploaded_by: uuid.UUID, original_filename: str, stored_filename: str, storage_path: str,
    file_size_bytes: int, sha256_hash: str,
) -> WorkspaceFile:
    row = WorkspaceFile(
        workspace_id=workspace_id, category_id=category_id, related_meeting_id=meeting_id,
        uploaded_by=uploaded_by, original_filename=original_filename, stored_filename=stored_filename,
        storage_path=storage_path, mime_type="application/pdf", extension="pdf",
        file_kind="document", origin_type="meeting_export",
        file_size_bytes=file_size_bytes, sha256_hash=sha256_hash,
        version_group_id=uuid.uuid4(), analysis_status="completed",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_meeting_exports(db: Session, workspace_id: uuid.UUID) -> list[tuple[WorkspaceFile, str]]:
    """(WorkspaceFile, meeting_title) 튜플 목록, 최신순."""
    return (
        db.query(WorkspaceFile, Meeting.title)
        .join(Meeting, Meeting.id == WorkspaceFile.related_meeting_id)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.origin_type == "meeting_export",
            WorkspaceFile.deleted_at.is_(None),
        )
        .order_by(WorkspaceFile.created_at.desc())
        .all()
    )

def list_files_by_meeting(db: Session, meeting_id: uuid.UUID) -> list[WorkspaceFile]:
    return (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.related_meeting_id == meeting_id,
            WorkspaceFile.deleted_at.is_(None),
            WorkspaceFile.is_latest.is_(True),
        )
        .order_by(WorkspaceFile.created_at.desc())
        .all()
    )