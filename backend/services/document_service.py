# backend/services/document_service.py

import hashlib
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile, BackgroundTasks
import httpx
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.db.modules import RoomFileLink

from backend.db.crud import ai_chat_crud, content_chunk_crud, contradiction_crud, document_crud, file_crud, meeting_crud, room_crud, similarity_crud
from backend.modules.rag.document_loader import load_document
from backend.modules.rag.chroma_client import delete_document as chroma_delete_document
from backend.routers.document_ws_router import broadcast_document_event, broadcast_document_event_sync
from backend.services import similarity_service


# 8003 문서 처리 서버 URL
DOCUMENT_PROCESS_URL = "http://61.81.98.86:8003/api/document"
DOCUMENT_PROCESS_BASE_URL = DOCUMENT_PROCESS_URL.rsplit("/api/document", 1)[0]


ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".hwpx", ".png", ".jpg", ".jpeg", ".docx", ".txt"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm"}

LOCAL_STORAGE_DIR = Path("storage/uploads/files")


# 검증 함수

def is_document_file(file: UploadFile) -> bool:
    suffix = Path(file.filename or "").suffix.lower()
    return suffix in ALLOWED_DOCUMENT_EXTENSIONS


def _is_valid_document_type(document_type: str) -> bool:
    return document_type in {"document", "meeting"}


def _is_audio_file(file: UploadFile) -> bool:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in AUDIO_EXTENSIONS:
        return True
    return bool(file.content_type and file.content_type.startswith("audio/"))


def _get_source(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".hwpx":
        return "hwpx"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "image"
    return suffix.replace(".", "") or "file"


# 응답 빌더

def _build_error_response(
    room_id: str | None,
    filename: str,
    document_type: str,
    message: str,
    error: str,
) -> dict:
    return {
        "status": "error",
        "room_id": room_id,
        "document_id": None,
        "filename": filename,
        "type": document_type,
        "storage_path": None,
        "summary": None,
        "link_status": None,
        "message": message,
        "error": error,
    }


# 로컬 파일 처리

def _safe_delete_local_file(file_path: str | None) -> bool:
    if not file_path:
        return False

    try:
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()
            return True
    except Exception as e:
        print(f"[document_service] 로컬 파일 삭제 실패: {file_path} / {repr(e)}")

    return False


def _save_file_to_local_storage(file_content: bytes, filename: str) -> tuple[str, str]:
    """원본 파일을 로컬에 저장하고 (storage_path, stored_filename)을 반환한다."""
    LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}{Path(filename).suffix}"
    storage_path = LOCAL_STORAGE_DIR / stored_filename
    storage_path.write_bytes(file_content)
    return str(storage_path), stored_filename


def _compute_sha256(file_content: bytes) -> str:
    return hashlib.sha256(file_content).hexdigest()


def _load_document_json(json_path: str) -> dict:
    if not json_path:
        return {}

    try:
        path = Path(json_path)
        if not path.exists() or not path.is_file():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            import json
            return json.load(f)

    except Exception as e:
        print(f"[document_service] 문서 JSON 읽기 실패: {json_path} / {repr(e)}")
        return {}


# 8003 서버 연동

def _delete_document_from_8003(external_document_id: str) -> dict:
    delete_url = f"{DOCUMENT_PROCESS_URL.rstrip('/')}/{external_document_id}"
    error_base = {
        "called": False,
        "url": delete_url,
        "status_code": None,
        "status": "error",
        "document_id": external_document_id,
        "deleted": {"file": False, "json": False},
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.delete(delete_url)

        try:
            response_data = response.json()
        except Exception:
            response_data = {
                "status": "error",
                "message": "8003 삭제 응답을 JSON으로 파싱할 수 없습니다.",
                "document_id": external_document_id,
                "deleted": {"file": False, "json": False},
                "error": response.text,
            }

        return {
            "called": True,
            "url": delete_url,
            "status_code": response.status_code,
            "status": response_data.get("status"),
            "message": response_data.get("message"),
            "document_id": response_data.get("document_id") or external_document_id,
            "deleted": response_data.get("deleted") or {"file": False, "json": False},
            "error": response_data.get("error"),
        }

    except httpx.RequestError as e:
        return {**error_base, "message": "8003 문서 삭제 서버에 연결할 수 없습니다.", "error": repr(e)}

    except Exception as e:
        return {**error_base, "message": "8003 문서 삭제 요청 중 오류가 발생했습니다.", "error": repr(e)}


# 데이터 추출 함수 (8003 응답 JSON 파싱 전용 — DB 스키마와 무관, 기존 그대로)

def _extract_keywords(document_json: dict) -> list[str]:
    metadata = document_json.get("metadata") or {}
    keywords = (
        document_json.get("keywords")
        or document_json.get("tags")
        or metadata.get("keywords")
        or metadata.get("tags")
        or []
    )

    if isinstance(keywords, str):
        return [keywords.strip()] if keywords.strip() else []

    if isinstance(keywords, list):
        return [str(k).strip() for k in keywords if str(k).strip()]

    return []


def _extract_chunks(document_json: dict) -> list[dict]:
    chunks = document_json.get("chunks") or []

    if not isinstance(chunks, list):
        return []

    result = []

    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue

        content = chunk.get("content") or chunk.get("text") or ""

        if not str(content).strip():
            continue

        metadata = chunk.get("metadata") or {}

        for key in ["font", "size", "bbox", "confidence"]:
            if key in chunk and key not in metadata:
                metadata[key] = chunk.get(key)

        result.append({
            "chunk_index": chunk.get("chunk_index", idx),
            "page_number": chunk.get("page_number"),
            "content_type": chunk.get("content_type") or chunk.get("type") or chunk.get("style") or "text",
            "content": str(content).strip(),
            "style": chunk.get("style"),
            "metadata": metadata,
        })

    return result


def _extract_tables_and_charts(document_json: dict) -> tuple[list, list]:
    tables = document_json.get("tables") or []
    charts = document_json.get("charts") or []

    if not tables and not charts:
        for page in document_json.get("page_results") or []:
            tables.extend(page.get("tables") or [])
            charts.extend(page.get("charts") or [])

    return tables, charts

def _extract_diagrams(document_json: dict) -> list:
    diagrams = document_json.get("diagrams") or []
    if not diagrams:
        for page in document_json.get("page_results") or []:
            diagrams.extend(page.get("diagrams") or [])
    return diagrams


def _build_figure_dicts(tables: list[dict], charts: list[dict], diagrams: list[dict]) -> list[dict]:
    """8003 응답의 표/차트/다이어그램을 DocumentFigure 저장용 딕셔너리로 변환한다.
    image_path가 없는 항목은 프론트에 띄울 이미지가 없으므로 제외한다.
    # TODO: image_path 상대경로를 8003이 실제로 이 base URL로 정적 서빙하는지
    # 나연 확인 필요 (예: "documents/figures/{doc_id}/{filename}")
    """
    figures = []
    for figure_type, items in (("table", tables), ("chart", charts), ("diagram", diagrams)):
        for item in items:
            image_path = item.get("image_path")
            if not image_path:
                continue
            figures.append({
                "page_number": item.get("page") or 0,
                "figure_type": figure_type,
                "image_url": f"{DOCUMENT_PROCESS_BASE_URL}/{image_path.lstrip('/')}",
            })
    return figures


def _extract_content_types(chunks: list[dict]) -> list[str]:
    content_types = []
    for chunk in chunks:
        content_type = chunk.get("content_type")
        if content_type and content_type not in content_types:
            content_types.append(content_type)
    return content_types


def _extract_analysis_metadata(document_json: dict) -> dict:
    metadata = document_json.get("metadata") or {}
    return {
        "page_count": document_json.get("page_count") or metadata.get("page_count"),
        "language": document_json.get("language") or metadata.get("language"),
        "confidence_score": document_json.get("confidence_score") or metadata.get("confidence_score"),
        "engines": document_json.get("engines") or metadata.get("engines") or [],
        "fallback_used": (
            document_json.get("fallback_used")
            if document_json.get("fallback_used") is not None
            else metadata.get("fallback_used")
        ),
    }


def _make_fallback_summary(original_text: str, max_length: int = 500) -> str:
    if not original_text:
        return ""

    lines = [line.strip() for line in original_text.strip().splitlines() if line.strip()]

    if not lines:
        return original_text.strip()[:max_length]

    summary_text = " ".join(lines[:8])
    return summary_text[:max_length].rstrip() + "..." if len(summary_text) > max_length else summary_text


# 문서 업로드 처리
# 문서 업로드 처리

async def upload_and_process_document(
    db, workspace_id, file, room_id=None, meeting_id=None, document_type="document",
    previous_file_id=None, current_user_id=None, background_tasks=None,
):
    filename = Path(file.filename).name if file and file.filename else "uploaded_file"

    try:
        if not current_user_id:
            raise PermissionError("인증 정보가 없습니다.")

        if _is_audio_file(file):
            return _build_error_response(
                room_id, filename, "voice",
                "음성 파일은 /api/stt/upload API를 사용해 주세요.",
                "use_stt_upload_api",
            )

        if not _is_valid_document_type(document_type):
            return _build_error_response(
                room_id, filename, document_type,
                "지원하지 않는 문서 유형입니다.", "unsupported_document_type",
            )

        if not is_document_file(file):
            return _build_error_response(
                room_id, filename, document_type,
                "지원하지 않는 파일 형식입니다.", "unsupported_file_type",
            )

        # room_id가 있으면 워크스페이스 소속인지 확인
        room = None
        if room_id:
            room = room_crud.get_room_by_id(db, UUID(room_id), workspace_id)
            if not room:
                raise PermissionError("채팅방을 찾을 수 없습니다.")

        # meeting_id가 있으면 워크스페이스 소속인지 확인
        meeting_uuid = None
        if meeting_id:
            meeting_uuid = UUID(meeting_id)
            meeting = meeting_crud.get_meeting(db, meeting_uuid)
            if not meeting or meeting.workspace_id != workspace_id:
                return _build_error_response(
                    room_id, filename, document_type,
                    "회의를 찾을 수 없습니다.", "meeting_not_found",
                )

        file_content = await file.read()
        sha256_hash = _compute_sha256(file_content)
        storage_path, stored_filename = _save_file_to_local_storage(file_content, filename)

        # 8003 문서 처리 서버 호출
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                DOCUMENT_PROCESS_URL,
                files={"file": (filename, file_content, file.content_type or "application/octet-stream")},
                data={"type": document_type},
            )
        response.raise_for_status()
        processed_result = response.json()

        external_document_id = processed_result.get("document_id") or processed_result.get("id")

        content_markdown = processed_result.get("content_markdown") or processed_result.get("content") or ""
        raw_chunks = processed_result.get("chunks") or []

        if not content_markdown.strip() and not (isinstance(raw_chunks, list) and raw_chunks):
            return _build_error_response(
                room_id, filename, document_type,
                "8003 문서 처리 결과에 content 또는 chunks가 없습니다.",
                "document_content_missing",
            )

        chunks = _extract_chunks(processed_result)
        tables, charts = _extract_tables_and_charts(processed_result)
        diagrams = _extract_diagrams(processed_result)
        analysis_metadata = _extract_analysis_metadata(processed_result)
        summary = processed_result.get("summary") or _make_fallback_summary(content_markdown)

        category = room_crud.get_default_category(db, workspace_id)
        if not category:
            raise RuntimeError("워크스페이스의 기본 카테고리를 찾을 수 없습니다.")

        # 1. workspace_files 저장
        workspace_file = file_crud.create_versioned_workspace_file(
            db,
            workspace_id=workspace_id,
            original_filename=filename,
            previous_file_id=previous_file_id,
            category_id=category.id,
            uploaded_by=UUID(current_user_id),
            stored_filename=stored_filename,
            storage_path=storage_path,
            mime_type=file.content_type,
            extension=Path(filename).suffix.lstrip("."),
            file_kind="document",
            origin_type="meeting_reference" if meeting_uuid else ("room_upload" if room_id else "document_analysis"),
            related_meeting_id=meeting_uuid,
            file_size_bytes=len(file_content),
            sha256_hash=sha256_hash,
            analysis_status="processing",
            external_ref=external_document_id,
        )

        # 2. document_analyses 저장
        # TODO: ocr_required_pages/ocr_success_pages/diagram_count는 8003 응답에
        # 대응 값이 없어서 임시로 채움 - 실제 응답 필드 확인 후 정확히 매핑할 것
        page_count = analysis_metadata.get("page_count") or 0
        document_crud.create_document_analysis(
            db,
            file_id=workspace_file.id,
            extracted_text=content_markdown,
            summary=summary,
            page_count=page_count,
            ocr_avg_confidence=analysis_metadata.get("confidence_score"),
            ocr_required_pages=page_count,
            ocr_success_pages=page_count,
            table_count=len(tables),
            graph_count=len(charts),
            diagram_count=len(diagrams),
            analysis_status="completed",
        )

        figures = _build_figure_dicts(tables, charts, diagrams)
        if figures:
            document_crud.create_document_figures(db, workspace_file.id, figures)

        # 3. 청크 생성 + ChromaDB 저장 (document_loader.py가 workspace_id/category_id 자동 조회)
        try:
            load_document(db, workspace_file.id, chunks=chunks)
            file_crud.update_analysis_status(db, workspace_file.id, "completed")
            document_dict = {
                "document_id": str(workspace_file.id),
                "filename": filename,
                "analysis_status": "completed",
                "created_at": workspace_file.created_at.isoformat() if workspace_file.created_at else None,
            }
            await broadcast_document_event(workspace_id, {"type": "document_added", "document": document_dict})
            background_tasks.add_task(
                similarity_service.compute_similarities_for_document_background,
                workspace_id, workspace_file.id,
            )
        except Exception as e:
            file_crud.update_analysis_status(db, workspace_file.id, "failed", error=repr(e))
            print(f"[document_service] ChromaDB 적재 실패: {repr(e)}")
            document_dict = {
                "document_id": str(workspace_file.id),
                "filename": filename,
                "analysis_status": "failed",
                "created_at": workspace_file.created_at.isoformat() if workspace_file.created_at else None,
            }
            await broadcast_document_event(workspace_id, {"type": "document_added", "document": document_dict})

        # 4. room에 연결 (room_id가 있을 때만)
        link_status = "not_applicable"
        if room:
            file_crud.link_file_to_room(db, room.id, workspace_file.id, UUID(current_user_id))
            link_status = "success"

        return {
            "status": "success",
            "workspace_id": str(workspace_id),
            "room_id": room_id,
            "meeting_id": meeting_id,
            "document_id": str(workspace_file.id),
            "filename": filename,
            "type": document_type,
            "storage_path": storage_path,
            "summary": summary,
            "link_status": link_status,
            "message": "문서 처리, 메타데이터 저장 및 ChromaDB 적재 요청이 완료되었습니다.",
            "error": None,
        }

    except PermissionError:
        raise
    except file_crud.FileVersionError:
        raise
    except httpx.HTTPStatusError as e:
        return _build_error_response(room_id, filename, document_type, "외부 처리 서버 응답 오류가 발생했습니다.", repr(e))
    except httpx.RequestError as e:
        return _build_error_response(room_id, filename, document_type, "외부 처리 서버에 연결할 수 없습니다.", repr(e))
    except Exception as e:
        return _build_error_response(room_id, filename, document_type, "문서 업로드 또는 처리 중 오류가 발생했습니다.", repr(e))

# 문서 재분석 (기존 저장 파일로 8003 재호출, 청크 재생성)
async def retry_document_analysis(db: Session, file_id: UUID, background_tasks: BackgroundTasks | None = None) -> dict:
    workspace_file = file_crud.get_file(db, file_id)
    if not workspace_file:
        raise PermissionError("재분석할 문서를 찾을 수 없습니다.")

    filename = workspace_file.original_filename

    try:
        file_crud.increment_retry_count(db, file_id)
        file_crud.update_analysis_status(db, file_id, "processing")

        try:
            with open(workspace_file.storage_path, "rb") as f:
                file_content = f.read()
        except OSError as e:
            file_crud.update_analysis_status(db, file_id, "failed", error=repr(e))
            await broadcast_document_event(
                workspace_file.workspace_id,
                {"type": "document_analysis_updated", "document": {
                    "document_id": str(file_id),
                    "filename": filename,
                    "analysis_status": "failed",
                    "created_at": workspace_file.created_at.isoformat() if workspace_file.created_at else None,
                }},
            )
            return _build_error_response(
                None, filename, workspace_file.origin_type,
                "원본 파일을 찾을 수 없어 재분석할 수 없습니다.", "source_file_missing",
            )

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                DOCUMENT_PROCESS_URL,
                files={"file": (filename, file_content, workspace_file.mime_type or "application/octet-stream")},
                data={"type": "document"},
            )
        response.raise_for_status()
        processed_result = response.json()

        content_markdown = processed_result.get("content_markdown") or processed_result.get("content") or ""
        raw_chunks = processed_result.get("chunks") or []

        if not content_markdown.strip() and not (isinstance(raw_chunks, list) and raw_chunks):
            file_crud.update_analysis_status(db, file_id, "failed", error="document_content_missing")
            await broadcast_document_event(
                workspace_file.workspace_id,
                {"type": "document_analysis_updated", "document": {
                    "document_id": str(file_id),
                    "filename": filename,
                    "analysis_status": "failed",
                    "created_at": workspace_file.created_at.isoformat() if workspace_file.created_at else None,
                }},
            )
            return _build_error_response(
                None, filename, workspace_file.origin_type,
                "8003 문서 처리 결과에 content 또는 chunks가 없습니다.", "document_content_missing",
            )

        chunks = _extract_chunks(processed_result)
        tables, charts = _extract_tables_and_charts(processed_result)
        diagrams = _extract_diagrams(processed_result)
        analysis_metadata = _extract_analysis_metadata(processed_result)
        summary = processed_result.get("summary") or _make_fallback_summary(content_markdown)
        page_count = analysis_metadata.get("page_count") or 0

        analysis_fields = {
            "extracted_text": content_markdown,
            "summary": summary,
            "page_count": page_count,
            "ocr_avg_confidence": analysis_metadata.get("confidence_score"),
            "ocr_required_pages": page_count,
            "ocr_success_pages": page_count,
            "table_count": len(tables),
            "graph_count": len(charts),
            "diagram_count": len(diagrams),
            "analysis_status": "completed",
        }

        if document_crud.get_document_analysis(db, file_id):
            document_crud.update_document_analysis(db, file_id, **analysis_fields)
        else:
            document_crud.create_document_analysis(db, file_id=file_id, **analysis_fields)

        document_crud.delete_figures_by_file(db, file_id)  # 재분석 시 중복 저장 방지
        figures = _build_figure_dicts(tables, charts, diagrams)
        if figures:
            document_crud.create_document_figures(db, file_id, figures)

        ai_chat_crud.delete_sources_by_file(db, file_id)
        contradiction_crud.delete_contradictions_by_reference_file(db, file_id)
        content_chunk_crud.delete_chunks_by_file(db, file_id)
        try:
            load_document(db, file_id, chunks=chunks)
            file_crud.update_analysis_status(db, file_id, "completed")
            await broadcast_document_event(
                workspace_file.workspace_id,
                {"type": "document_analysis_updated", "document": {
                    "document_id": str(file_id),
                    "filename": filename,
                    "analysis_status": "completed",
                    "created_at": workspace_file.created_at.isoformat() if workspace_file.created_at else None,
                }},
            )
            if background_tasks is not None:
                background_tasks.add_task(
                    similarity_service.compute_similarities_for_document_background,
                    workspace_file.workspace_id, file_id,
                )
        except Exception as e:
            file_crud.update_analysis_status(db, file_id, "failed", error=repr(e))
            print(f"[document_service] 재분석 ChromaDB 적재 실패: {repr(e)}")
            await broadcast_document_event(
                workspace_file.workspace_id,
                {"type": "document_analysis_updated", "document": {
                    "document_id": str(file_id),
                    "filename": filename,
                    "analysis_status": "failed",
                    "created_at": workspace_file.created_at.isoformat() if workspace_file.created_at else None,
                }},
            )

        return {
            "status": "success",
            "document_id": str(file_id),
            "filename": filename,
            "summary": summary,
            "message": "문서 재분석이 완료되었습니다.",
            "error": None,
        }

    except PermissionError:
        raise
    except httpx.HTTPStatusError as e:
        db.rollback()
        file_crud.update_analysis_status(db, file_id, "failed", error=repr(e))
        return _build_error_response(None, filename, workspace_file.origin_type, "외부 처리 서버 응답 오류가 발생했습니다.", repr(e))
    except httpx.RequestError as e:
        db.rollback()
        file_crud.update_analysis_status(db, file_id, "failed", error=repr(e))
        return _build_error_response(None, filename, workspace_file.origin_type, "외부 처리 서버에 연결할 수 없습니다.", repr(e))
    except Exception as e:
        db.rollback()
        file_crud.update_analysis_status(db, file_id, "failed", error=repr(e))
        return _build_error_response(None, filename, workspace_file.origin_type, "문서 재분석 중 오류가 발생했습니다.", repr(e))
    
async def analyze_worktree_file_background(file_id: UUID) -> None:
    """
    워크트리(폴더) 업로드로 등록된 문서/이미지 파일을 백그라운드에서 분석한다.

    worktree_router.upload_worktree()는 파일 등록만 하고 analysis_status="pending"으로
    남기므로(코드/설정 파일 분석 로직이 아직 없어 워크트리 자체는 등록 단계에서 끝남),
    문서/이미지 파일만 여기서 기존 retry_document_analysis()를 재사용해 분석을 이어서 실행한다.

    요청 스코프 db 세션은 응답 반환 후 닫히므로, 백그라운드 실행을 위해 별도 세션을 새로 연다.
    개별 파일 분석 실패가 다른 파일이나 worktree 상태에 영향을 주지 않도록 예외를 여기서 흡수한다.
    """
    db = SessionLocal()
    try:
        await retry_document_analysis(db, file_id)
        workspace_file = file_crud.get_file(db, file_id)
        if workspace_file:
            similarity_service.compute_similarities_for_document(
                db, workspace_file.workspace_id, file_id,
            )
    except Exception as e:
        print(f"[document_service] 워크트리 파일 자동 분석 실패: file_id={file_id}, error={repr(e)}")
    finally:
        # 성공/실패 어느 쪽이든 analysis_status는 이미 확정됐으므로,
        # 이 파일이 속한 워크트리가 이제 전부 settle됐는지 확인해 상태를 갱신한다.
        workspace_file = file_crud.get_file(db, file_id)
        if workspace_file and workspace_file.worktree_id:
            file_crud.finalize_worktree_status_if_analysis_done(db, workspace_file.worktree_id)
        db.close()


# 문서 상세 조회
# 참고: 기존과 달리 tables/charts/keywords/organized_items(연결된 업무 목록)는
# 새 스키마에 저장 위치가 없어서 응답에서 뺐다. 필요하면 별도로 저장 구조를 논의해야 한다.

def get_document_detail(db: Session, file_id: UUID) -> dict:
    try:
        workspace_file = file_crud.get_file(db, file_id)
        if not workspace_file:
            raise PermissionError("문서를 찾을 수 없습니다.")

        analysis = document_crud.get_document_analysis(db, file_id)
        chunks = content_chunk_crud.get_chunks_by_file(db, file_id)

        return {
            "status": "success",
            "document_id": str(file_id),
            "document": {
                "document_id": str(workspace_file.id),
                "workspace_id": str(workspace_file.workspace_id),
                "filename": workspace_file.original_filename,
                "file_kind": workspace_file.file_kind,
                "analysis_status": workspace_file.analysis_status,
                "created_at": workspace_file.created_at,
                "raw": {
                    "original_text": analysis.extracted_text if analysis else None,
                    "chunks": [
                        {"chunk_index": c.chunk_index, "content": c.chunk_text, "page_number": c.page_number}
                        for c in chunks
                    ],
                },
                "analysis": {
                    "summary": analysis.summary if analysis else None,
                    "page_count": analysis.page_count if analysis else None,
                    "table_count": analysis.table_count if analysis else None,
                    "graph_count": analysis.graph_count if analysis else None,
                    "ocr_avg_confidence": float(analysis.ocr_avg_confidence) if analysis and analysis.ocr_avg_confidence else None,
                },
            },
            "message": "문서 상세 조회가 완료되었습니다.",
            "error": None,
        }

    except PermissionError:
        raise

    except Exception as e:
        return {
            "status": "error",
            "document_id": str(file_id),
            "document": None,
            "message": "문서 상세 조회 중 오류가 발생했습니다.",
            "error": repr(e),
        }


# 문서 삭제

def delete_processed_document(db: Session, file_id: UUID) -> dict:
    try:
        workspace_file = file_crud.get_file(db, file_id)
        if not workspace_file:
            raise PermissionError("삭제할 문서를 찾을 수 없습니다.")

        contradiction_crud.delete_contradictions_by_reference_file(db, file_id)
        ai_chat_crud.delete_sources_by_file(db, file_id)
        deleted_chunks_count = content_chunk_crud.delete_chunks_by_file(db, file_id)
        deleted_local_source_file = _safe_delete_local_file(workspace_file.storage_path)

        document_8003_result = None
        if workspace_file.external_ref:
            document_8003_result = _delete_document_from_8003(workspace_file.external_ref)
            if document_8003_result.get("status") == "error":
                print(f"[document_service] 8003 원본 삭제 실패: {document_8003_result}")

        try:
            chroma_delete_document(str(file_id), str(workspace_file.workspace_id))
            chroma_deleted = True
            print(f"[document_service] ChromaDB 벡터 삭제 완료: {file_id}")
        except Exception as e:
            chroma_deleted = False
            print(f"[document_service] ChromaDB 벡터 삭제 실패: {repr(e)}")

        similarity_crud.delete_similarities_for_file(db, file_id)
        file_crud.delete_file(db, file_id)

        broadcast_document_event_sync(
            workspace_file.workspace_id,
            {"type": "document_removed", "document_id": str(file_id)},
        )
        
        return {
            "status": "success",
            "document_id": str(file_id),
            "message": "문서 삭제가 완료되었습니다.",
            "deleted": {
                "content_chunks": deleted_chunks_count,
                "local_source_file": deleted_local_source_file,
                "chroma": chroma_deleted,
                "document_8003": document_8003_result,
            },
            "error": None,
        }

    except PermissionError:
        raise

    except Exception as e:
        return {
            "status": "error",
            "document_id": str(file_id),
            "message": "문서 삭제 중 오류가 발생했습니다.",
            "deleted": None,
            "error": repr(e),
        }
    
def unlink_or_delete_meeting_document(db: Session, file_id: UUID, meeting_id: UUID) -> dict:
    """회의 첨부 문서를 삭제한다. 채팅방에도 연결된 문서면 회의 연결만 해제하고,
    그 회의만을 위해 올라온 문서면 완전히 삭제(RAG/모순 참조 정리 포함)한다."""
    workspace_file = file_crud.get_file(db, file_id)
    if not workspace_file or workspace_file.related_meeting_id != meeting_id:
        raise PermissionError("회의에 첨부된 문서를 찾을 수 없습니다.")

    has_room_link = (
        db.query(RoomFileLink).filter(RoomFileLink.file_id == file_id).first() is not None
    )
    if has_room_link:
        workspace_file.related_meeting_id = None
        db.commit()
        return {"status": "unlinked", "file_id": str(file_id)}

    return delete_processed_document(db, file_id)