import os
import json
from pathlib import Path

from fastapi import UploadFile
import httpx

from backend.db.crud import (
    create_conversation,
    get_conversation_by_id,
    save_document_metadata,
    get_document_by_id_for_user,
    get_tasks_by_document,
    delete_document_for_user,
    delete_document_chunks,
    update_chroma_status,
    link_document_to_room,
)
from backend.modules.rag.document_loader import load_document
from backend.modules.rag.chroma_client import delete_document as chroma_delete_document


# 8003 문서 처리 서버 URL
DOCUMENT_PROCESS_URL = os.getenv(
    "DOCUMENT_PROCESS_URL",
    "http://61.81.98.86:8003/api/document"
)

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".hwpx", ".png", ".jpg", ".jpeg"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm"}


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
    conversation_id: str | None,
    filename: str,
    document_type: str,
    message: str,
    error: str,
) -> dict:
    return {
        "status": "error",
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "document_id": None,
        "filename": filename,
        "type": document_type,
        "file_path": None,
        "json_path": None,
        "summary": None,
        "chroma_load_result": None,
        "chroma_status": None,
        "link_status": None,
        "warning": None,
        "message": message,
        "error": error,
    }


# 로컬 파일 처리

def _safe_delete_local_file(file_path: str) -> bool:
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


def _save_processed_result_to_local_json(processed_result: dict, document_id: str) -> str:
    local_json_dir = Path("data/uploads/documents")
    local_json_dir.mkdir(parents=True, exist_ok=True)
    local_json_path = local_json_dir / f"{document_id}.json"

    processed_result["original_json_path"] = processed_result.get("json_path") or ""
    processed_result["json_path"] = str(local_json_path)

    with open(local_json_path, "w", encoding="utf-8") as f:
        json.dump(processed_result, f, ensure_ascii=False, indent=2)

    return str(local_json_path)


def _load_document_json(json_path: str) -> dict:
    if not json_path:
        return {}

    try:
        path = Path(json_path)
        if not path.exists() or not path.is_file():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"[document_service] 문서 JSON 읽기 실패: {json_path} / {repr(e)}")
        return {}


# 8003 서버 연동

def _delete_document_from_8003(document_id: str) -> dict:
    delete_url = f"{DOCUMENT_PROCESS_URL.rstrip('/')}/{document_id}"
    error_base = {
        "called": False,
        "url": delete_url,
        "status_code": None,
        "status": "error",
        "document_id": document_id,
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
                "document_id": document_id,
                "deleted": {"file": False, "json": False},
                "error": response.text,
            }

        return {
            "called": True,
            "url": delete_url,
            "status_code": response.status_code,
            "status": response_data.get("status"),
            "message": response_data.get("message"),
            "document_id": response_data.get("document_id") or document_id,
            "deleted": response_data.get("deleted") or {"file": False, "json": False},
            "error": response_data.get("error"),
        }

    except httpx.RequestError as e:
        return {**error_base, "message": "8003 문서 삭제 서버에 연결할 수 없습니다.", "error": repr(e)}

    except Exception as e:
        return {**error_base, "message": "8003 문서 삭제 요청 중 오류가 발생했습니다.", "error": repr(e)}


# 데이터 추출 함수

def _extract_original_text(document: dict, document_json: dict) -> str:
    content = (
        document.get("content_markdown")
        or document_json.get("content_markdown")
        or document_json.get("content")
        or ""
    )

    if content and content.strip():
        return content

    chunks = document_json.get("chunks") or []

    if isinstance(chunks, list):
        chunk_texts = [
            chunk.get("content") or chunk.get("text") or ""
            for chunk in chunks
            if isinstance(chunk, dict)
        ]
        return "\n\n".join(t.strip() for t in chunk_texts if t.strip())

    return ""


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


def _extract_organized_items(document_json: dict) -> dict:
    return {
        "important_points": (
            document_json.get("important_points")
            or document_json.get("key_points")
            or document_json.get("main_points")
            or []
        ),
        "decisions": (
            document_json.get("decisions")
            or document_json.get("decision_items")
            or []
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

async def _process_document_file(
    file: UploadFile,
    conversation_id: str,
    document_type: str,
    user_id: str,
) -> dict:
    filename = Path(file.filename).name if file.filename else "uploaded_file"
    file_content = await file.read()

    async with httpx.AsyncClient(timeout=300.0) as client:
        form_data = {
            "type": document_type,
            "room_id": conversation_id or "",  # TODO: 8003 v1 호환용, 추후 제거 예정
            "conversation_id": conversation_id or "",
        }
        response = await client.post(
            DOCUMENT_PROCESS_URL,
            files={"file": (filename, file_content, file.content_type or "application/octet-stream")},
            data=form_data,
        )

    response.raise_for_status()
    processed_result = response.json()

    document_id = processed_result.get("document_id") or processed_result.get("id")
    result_conversation_id = conversation_id
    result_filename = processed_result.get("filename") or processed_result.get("title") or filename
    result_type = processed_result.get("type") or document_type
    file_path = processed_result.get("file_path") or ""
    summary = processed_result.get("summary") or ""
    content_markdown = processed_result.get("content_markdown") or processed_result.get("content") or ""
    chunks = processed_result.get("chunks") or []

    if not document_id:
        return {
            "status": "error",
            "room_id": result_conversation_id,  # TODO: v1 호환용, 추후 제거 예정
            "conversation_id": result_conversation_id,
            "document_id": None,
            "filename": result_filename,
            "type": result_type,
            "file_path": file_path,
            "json_path": processed_result.get("json_path") or "",
            "summary": summary,
            "chroma_load_result": None,
            "chroma_status": None,
            "link_status": None,
            "warning": None,
            "message": "8003 문서 처리 결과에 document_id가 없습니다.",
            "error": "document_id_missing",
        }

    if not content_markdown.strip() and not (isinstance(chunks, list) and chunks):
        return {
            "status": "error",
            "room_id": result_conversation_id,  # TODO: v1 호환용, 추후 제거 예정
            "conversation_id": result_conversation_id,
            "document_id": document_id,
            "filename": result_filename,
            "type": result_type,
            "file_path": file_path,
            "json_path": processed_result.get("json_path") or "",
            "summary": summary,
            "chroma_load_result": None,
            "chroma_status": None,
            "link_status": None,
            "warning": None,
            "message": "8003 문서 처리 결과에 content 또는 chunks가 없습니다.",
            "error": "document_content_missing",
        }

    processed_result["content_markdown"] = content_markdown
    json_path = _save_processed_result_to_local_json(processed_result, document_id)

    saved_document_id = save_document_metadata({
        "id": document_id,
        "conversation_id": result_conversation_id or "",
        "title": result_filename,
        "type": result_type,
        "source": _get_source(result_filename),
        "file_path": file_path,
        "json_path": json_path,
        "summary": summary,
        "status": "processed",
        "notion_url": "",
        "error": "",
    })

    try:
        chroma_load_result = load_document(
            document_id=saved_document_id,
            room_id=result_conversation_id or "",  # TODO: RAG loader v1 호환용
        )
        chroma_status = "success" if chroma_load_result.get("status") == "success" else "failed"
        update_chroma_status(saved_document_id, chroma_status)
        print(f"[document_service] ChromaDB 적재 결과: {chroma_load_result}")
    except Exception as e:
        chroma_status = "failed"
        chroma_load_result = {
            "status": "error",
            "chunk_count": 0,
            "document_id": saved_document_id,
            "error": repr(e),
        }
        update_chroma_status(saved_document_id, "failed")
        print(f"[document_service] ChromaDB 적재 실패: {repr(e)}")

    link_status = "success"
    link_warning = None

    # conversation_id가 있으면 room_document_links에 연결 추가 (ChromaDB 성공 여부와 무관)
    # TODO: CRUD 함수명은 아직 room 기준이므로 추후 conversation 기준 이름으로 변경 예정
    linked = link_document_to_room(
        room_id=result_conversation_id,
        document_id=saved_document_id,
        user_id=user_id,
    )

    if linked:
        print(f"[document_service] room_document_links 연결 완료: {result_conversation_id} → {saved_document_id}")
    else:
        link_status = "failed"
        link_warning = "문서는 저장되었지만 사건방-문서 연결에 실패했습니다."
        print(f"[document_service] room_document_links 연결 실패: {result_conversation_id} → {saved_document_id}")

    final_status = "success" if link_status == "success" else "partial_success"

    return {
        "status": final_status,
        "room_id": result_conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": result_conversation_id,
        "document_id": saved_document_id,
        "filename": result_filename,
        "type": result_type,
        "file_path": file_path,
        "json_path": json_path,
        "summary": summary,
        "chroma_load_result": chroma_load_result,
        "chroma_status": chroma_status,
        "link_status": link_status,
        "warning": link_warning,
        "message": "문서 처리, 메타데이터 저장 및 ChromaDB 적재 요청이 완료되었습니다.",
        "error": None,
    }


async def upload_and_process_document(
    file: UploadFile,
    conversation_id: str | None = None,
    room_id: str | None = None,  # TODO: v1 호환용, 추후 제거 예정
    document_type: str = "document",
    user_id: str | None = None,
) -> dict:
    filename = Path(file.filename).name if file and file.filename else "uploaded_file"
    resolved_conversation_id = conversation_id or room_id

    try:
        if not user_id:
            raise PermissionError("인증 정보가 없습니다.")

        if _is_audio_file(file):
            return _build_error_response(
                resolved_conversation_id,
                filename,
                "voice",
                "음성 파일은 /api/stt/upload API를 사용해 주세요.",
                "use_stt_upload_api",
            )

        if not _is_valid_document_type(document_type):
            return _build_error_response(
                resolved_conversation_id,
                filename,
                document_type,
                "지원하지 않는 문서 유형입니다.",
                "unsupported_document_type",
            )

        if not is_document_file(file):
            return _build_error_response(
                resolved_conversation_id,
                filename,
                document_type,
                "지원하지 않는 파일 형식입니다.",
                "unsupported_file_type",
            )

        # conversation_id가 있으면 현재 사용자 소유 채팅방인지 확인
        if resolved_conversation_id:
            conversation = get_conversation_by_id(resolved_conversation_id, user_id)

            if not conversation:
                raise PermissionError("채팅방을 찾을 수 없습니다.")

        # conversation_id가 없으면 현재 사용자 기준 새 채팅방 생성
        else:
            resolved_conversation_id = create_conversation(
                title=filename,
                user_id=user_id,
            )

        return await _process_document_file(
            file=file,
            conversation_id=resolved_conversation_id,
            document_type=document_type,
            user_id=user_id,
        )

    except PermissionError:
        raise

    except httpx.HTTPStatusError as e:
        return _build_error_response(
            resolved_conversation_id,
            filename,
            document_type,
            "외부 처리 서버 응답 오류가 발생했습니다.",
            repr(e),
        )

    except httpx.RequestError as e:
        return _build_error_response(
            resolved_conversation_id,
            filename,
            document_type,
            "외부 처리 서버에 연결할 수 없습니다.",
            repr(e),
        )

    except Exception as e:
        return _build_error_response(
            resolved_conversation_id,
            filename,
            document_type,
            "문서 업로드 또는 처리 중 오류가 발생했습니다.",
            repr(e),
        )


# 문서 상세 조회

def get_document_detail(document_id: str, user_id: str) -> dict:
    try:
        document = get_document_by_id_for_user(document_id, user_id)

        if not document:
            raise PermissionError("문서를 찾을 수 없습니다.")

        document_json = _load_document_json(document.get("json_path") or "")
        original_text = _extract_original_text(document, document_json)
        chunks = _extract_chunks(document_json)
        tables, charts = _extract_tables_and_charts(document_json)
        keywords = _extract_keywords(document_json)
        analysis_metadata = _extract_analysis_metadata(document_json)
        content_types = _extract_content_types(chunks)
        summary = (
            document.get("summary")
            or document_json.get("summary")
            or _make_fallback_summary(original_text)
        )
        tasks = get_tasks_by_document(document_id)
        organized_items = _extract_organized_items(document_json)

        return {
            "status": "success",
            "document_id": document_id,
            "document": {
                "document_id": document.get("id"),
                "room_id": document.get("conversation_id"),  # TODO: v1 호환용, 추후 제거 예정
                "conversation_id": document.get("conversation_id"),
                "filename": document.get("title"),
                "type": document.get("type"),
                "source": document.get("source"),
                "status": document.get("status"),
                "chroma_status": document.get("chroma_status"),
                "file_path": document.get("file_path"),
                "json_path": document.get("json_path"),
                "created_at": document.get("created_at"),
                "raw": {
                    "original_text": original_text,
                    "chunks": chunks,
                    "tables": tables,
                    "charts": charts,
                },
                "analysis": {
                    "summary": summary,
                    "keywords": keywords,
                    "page_count": analysis_metadata.get("page_count"),
                    "content_types": content_types,
                    "language": analysis_metadata.get("language"),
                    "confidence_score": analysis_metadata.get("confidence_score"),
                    "engines": analysis_metadata.get("engines"),
                    "fallback_used": analysis_metadata.get("fallback_used"),
                },
                "organized": {
                    "tasks": [
                        {
                            "task_id": task.get("id"),
                            "document_id": task.get("document_id"),
                            "room_id": task.get("conversation_id"),  # TODO: v1 호환용, 추후 제거 예정
                            "conversation_id": task.get("conversation_id"),
                            "task": task.get("task"),
                            "assignee": task.get("assignee"),
                            "deadline": task.get("deadline"),
                            "status": task.get("status"),
                            "priority": task.get("priority"),
                            "created_at": task.get("created_at"),
                        }
                        for task in tasks
                    ],
                    "important_points": organized_items.get("important_points", []),
                    "decisions": organized_items.get("decisions", []),
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
            "document_id": document_id,
            "document": None,
            "message": "문서 상세 조회 중 오류가 발생했습니다.",
            "error": repr(e),
        }


# 문서 삭제

def delete_processed_document(document_id: str, user_id: str) -> dict:
    try:
        document = get_document_by_id_for_user(document_id, user_id)

        if not document:
            raise PermissionError("삭제할 문서를 찾을 수 없습니다.")

        json_path = document.get("json_path") or ""
        file_path = document.get("file_path") or ""

        document_server_result = _delete_document_from_8003(document_id)
        external_deleted = document_server_result.get("deleted") or {}

        deleted_chunks_count = delete_document_chunks(document_id)
        deleted_local_json_file = _safe_delete_local_file(json_path)
        deleted_local_source_file = _safe_delete_local_file(file_path)

        try:
            chroma_delete_document(document_id)
            chroma_deleted = True
            print(f"[document_service] ChromaDB 벡터 삭제 완료: {document_id}")
        except Exception as e:
            chroma_deleted = False
            print(f"[document_service] ChromaDB 벡터 삭제 실패: {repr(e)}")

        deleted_document = delete_document_for_user(document_id, user_id)

        server_status = document_server_result.get("status")

        if server_status == "success":
            final_status = "success"
            message = "문서 삭제가 완료되었습니다."
            error = None
        elif server_status == "partial_success":
            final_status = "partial_success"
            message = "8000 문서는 삭제되었지만, 8003 서버에서 일부 파일만 삭제되었습니다."
            error = document_server_result.get("error")
        else:
            final_status = "partial_success"
            message = "8000 문서는 삭제되었지만, 8003 서버 원본 삭제는 실패했습니다."
            error = document_server_result.get("error")

        return {
            "status": final_status,
            "document_id": document_id,
            "message": message,
            "deleted": {
                "document_chunks": deleted_chunks_count,
                "document": deleted_document,
                "local_json_file": deleted_local_json_file,
                "local_source_file": deleted_local_source_file,
                "external_file": bool(external_deleted.get("file")),
                "external_json": bool(external_deleted.get("json")),
                "chroma": chroma_deleted,
            },
            "document_server_result": document_server_result,
            "error": error,
        }

    except PermissionError:
        raise

    except Exception as e:
        return {
            "status": "error",
            "document_id": document_id,
            "message": "문서 삭제 중 오류가 발생했습니다.",
            "deleted": None,
            "document_server_result": None,
            "error": repr(e),
        }