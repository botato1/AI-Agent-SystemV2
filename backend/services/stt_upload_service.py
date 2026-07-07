import json
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import UploadFile

from backend.db.crud import (
    create_conversation,
    get_conversation_by_id,
    save_document_metadata,
    save_document_chunks,
    delete_document_chunks,
    get_document_by_id_for_user,
    get_document_chunks,
    get_voice_documents_for_user,
    delete_document_for_user,
    update_chroma_status,
    link_document_to_room,
)
from backend.modules.rag.document_loader import (
    _load_voice,
    _get_upload_context,
    _build_base_meta,
)
from backend.modules.rag.chroma_client import delete_document as chroma_delete_document


# room_id 없이 업로드된 음성의 conversation_id 내부 값 (conversations 테이블에 생성하지 않음)
VOICE_LIBRARY_ROOM_ID = "__voice_library__"

# 8001 STT 서버 URL
STT_BASE_URL = os.getenv("STT_BASE_URL", "http://192.168.0.32:8001")
STT_PROCESS_URL = os.getenv("STT_PROCESS_URL", f"{STT_BASE_URL}/api/stt")

# 허용할 음성 확장자
ALLOWED_STT_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm"}


# 검증 함수

def is_allowed_stt_file(file: UploadFile) -> bool:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in ALLOWED_STT_EXTENSIONS:
        return True
    return bool(file.content_type and file.content_type.startswith("audio/"))


def _is_voice_library_room_id(conversation_id: str | None) -> bool:
    return conversation_id == VOICE_LIBRARY_ROOM_ID


# 데이터 변환 함수

# 초 단위 시간을 문자열로 변환 (값이 없으면 ? 표시)
def _format_time(value) -> str:
    if value is None:
        return "?"
    try:
        return f"{float(value):.2f}s"
    except Exception:
        return str(value)


# documents.metadata JSON 문자열을 dict로 변환
def _safe_json_loads(value) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


# STT 결과로 LLM/RAG용 content_markdown 생성
def _build_stt_content_markdown(data: dict) -> str:
    metadata = data.get("metadata") or {}
    title = metadata.get("original_filename") or data.get("title") or "STT 결과"
    content = data.get("content") or ""
    transcription = data.get("transcription") or []

    lines = [
        f"# {title}",
        "",
        "## 전체 전사 내용",
        "",
        content.strip() if content else "",
        "",
        "## 화자별 전사",
        "",
    ]

    if transcription:
        for item in transcription:
            text = item.get("text") or ""
            if not text.strip():
                continue

            lines.append(
                f"- [{_format_time(item.get('start'))} ~ {_format_time(item.get('end'))}] "
                f"{item.get('speaker') or 'UNKNOWN'}: {text.strip()}"
            )
    else:
        lines.append("- 전사 상세 정보가 없습니다.")

    return "\n".join(lines).strip()


# STT metadata에서 duration 값 추출 (키 이름이 다를 수 있어 안전하게 처리)
def _get_duration_sec(metadata: dict) -> float | None:
    if not metadata:
        return None

    duration = (
        metadata.get("duration_sec")
        or metadata.get("duration")
        or metadata.get("total_duration_sec")
    )

    if duration is None:
        return None

    try:
        return float(duration)
    except Exception:
        return None


# STT 응답에서 원본 파일명 추출
def _get_stt_filename(data: dict, fallback_filename: str) -> str:
    metadata = data.get("metadata") or {}
    return (
        metadata.get("original_filename")
        or data.get("filename")
        or data.get("title")
        or fallback_filename
    )


# STT 응답에서 파일 경로 추출
def _get_stt_file_path(data: dict) -> str:
    metadata = data.get("metadata") or {}
    return metadata.get("original_file_url") or data.get("file_path") or ""


# original_file_url에서 8001 삭제 API용 file_id 추출
def _extract_file_id_from_original_file_url(original_file_url: str | None) -> str | None:
    if not original_file_url:
        return None

    try:
        filename = Path(urlparse(original_file_url).path).name
        return Path(filename).stem if filename else None
    except Exception:
        return None


# 8001 DELETE 호출용 file_id 결정 (original_file_url → metadata.file_id → document_id 순)
def _resolve_stt_file_id(document_id: str, metadata: dict) -> str:
    metadata = metadata or {}

    return (
        _extract_file_id_from_original_file_url(metadata.get("original_file_url"))
        or metadata.get("file_id")
        or document_id
    )


# document_chunks 조회 결과를 프론트 transcription 형식으로 변환
def _chunks_to_transcription(chunks: list[dict]) -> list[dict]:
    return [
        {
            "chunk_id": chunk.get("id"),
            "chunk_index": chunk.get("chunk_index"),
            "start": chunk.get("start_time"),
            "end": chunk.get("end_time"),
            "speaker": chunk.get("speaker"),
            "text": chunk.get("content") or "",
            "user_edited": bool(chunk.get("user_edited")),
        }
        for chunk in chunks
    ]


# 로컬 JSON 처리

# STT 결과를 로컬 JSON으로 저장 (서버 이관 후 NAS 경로로 변경 예정)
def _save_stt_result_to_local_json(
    document_id: str,
    content_markdown: str,
    transcription: list,
    metadata: dict,
    title: str,
    summary: str,
) -> str:
    local_json_dir = Path("data/uploads/voice")
    local_json_dir.mkdir(parents=True, exist_ok=True)
    local_json_path = local_json_dir / f"{document_id}.json"

    with open(local_json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "id": document_id,
                "title": title,
                "type": "voice",
                "source": "voice",
                "content": content_markdown,
                "content_markdown": content_markdown,
                "transcription": transcription,
                "metadata": metadata,
                "summary": summary,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    return str(local_json_path)


# 로컬 JSON에서 STT 결과 읽기
def _load_stt_json(json_path: str) -> dict:
    if not json_path:
        return {}

    try:
        path = Path(json_path)

        if not path.exists() or not path.is_file():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        print(f"[stt_upload_service] STT JSON 읽기 실패: {json_path} / {repr(e)}")
        return {}


# 로컬 JSON에서 전체 전사 텍스트 추출
def _extract_plain_content_from_json(stt_json: dict) -> str:
    content_markdown = stt_json.get("content_markdown") or stt_json.get("content") or ""

    if not content_markdown:
        return ""

    marker = "## 전체 전사 내용"
    next_marker = "## 화자별 전사"

    if marker not in content_markdown:
        return content_markdown.strip()

    content_part = content_markdown.split(marker, 1)[1]

    if next_marker in content_part:
        content_part = content_part.split(next_marker, 1)[0]

    return content_part.strip()


# 응답 빌더

def _build_success_response(
    conversation_id: str | None,
    document_id: str,
    filename: str,
    title: str,
    file_path: str,
    summary: str,
    saved_chunk_count: int,
    transcription: list,
    metadata: dict,
    chroma_status: str,
    link_status: str = "success",
    warning: str | None = None,
) -> dict:
    return {
        "status": "success" if link_status == "success" else "partial_success",
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "document_id": document_id,
        "file_id": _resolve_stt_file_id(document_id, metadata),
        "filename": filename,
        "title": title,
        "type": "voice",
        "source": "voice",
        "file_path": file_path,
        "summary": summary,
        "chunk_count": saved_chunk_count,
        "chroma_status": chroma_status,
        "link_status": link_status,
        "warning": warning,
        "duration_sec": _get_duration_sec(metadata),
        "transcription": transcription,
        "metadata": metadata,
        "message": "STT 처리 및 메타데이터 저장이 완료되었습니다.",
        "error": None,
    }


def _build_error_response(
    conversation_id: str | None,
    filename: str,
    message: str,
    error: str,
) -> dict:
    return {
        "status": "error",
        "room_id": conversation_id,  # TODO: v1 호환용, 추후 제거 예정
        "conversation_id": conversation_id,
        "document_id": None,
        "file_id": None,
        "filename": filename,
        "title": None,
        "type": "voice",
        "source": "voice",
        "file_path": None,
        "summary": None,
        "chunk_count": 0,
        "chroma_status": None,
        "link_status": None,
        "warning": None,
        "duration_sec": None,
        "transcription": [],
        "metadata": None,
        "message": message,
        "error": error,
    }


# STT 업로드 처리

# STT 업로드 통합 처리 (파일 검증 → 8001 STT → 로컬 JSON 저장 → DB 저장 → ChromaDB 적재)
async def upload_and_process_stt(
    file: UploadFile,
    conversation_id: str | None = None,
    room_id: str | None = None,  # TODO: v1 호환용, 추후 제거 예정
    user_id: str | None = None,
) -> dict:
    filename = Path(file.filename).name if file and file.filename else "uploaded_audio"
    resolved_conversation_id = conversation_id or room_id

    try:
        if not user_id:
            raise PermissionError("인증 정보가 없습니다.")

        if not is_allowed_stt_file(file):
            return _build_error_response(
                resolved_conversation_id,
                filename,
                "지원하지 않는 음성 파일 형식입니다.",
                "unsupported_stt_file_type",
            )

        # conversation_id가 있으면 현재 사용자 소유 채팅방인지 먼저 확인
        # 권한 없는 conversation_id면 8001 STT 서버 호출 전에 차단한다.
        if resolved_conversation_id:
            conversation = get_conversation_by_id(resolved_conversation_id, user_id)

            if not conversation:
                raise PermissionError("채팅방을 찾을 수 없습니다.")

        file_content = await file.read()

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                STT_PROCESS_URL,
                files={
                    "file": (
                        filename,
                        file_content,
                        file.content_type or "application/octet-stream",
                    )
                },
                data={"topic": ""},
            )

        response.raise_for_status()
        stt_result = response.json()

        if stt_result.get("status") != "success":
            return _build_error_response(
                resolved_conversation_id,
                filename,
                stt_result.get("message") or "STT 처리에 실패했습니다.",
                str(stt_result.get("error") or "stt_process_failed"),
            )

        data = stt_result.get("data") or {}

        if not data:
            return _build_error_response(
                resolved_conversation_id,
                filename,
                "STT 서버 응답에 data가 없습니다.",
                "stt_data_missing",
            )

        document_id = data.get("id")
        title = data.get("title") or filename
        result_filename = _get_stt_filename(data, filename)
        file_path = _get_stt_file_path(data)
        summary = data.get("summary") or ""
        status = data.get("status") or "processed"
        error = data.get("error") or ""
        transcription = data.get("transcription") or []
        metadata = data.get("metadata") or {}

        if data.get("language") and not metadata.get("language"):
            metadata["language"] = data.get("language")

        content_markdown = _build_stt_content_markdown(data)

        if not document_id:
            return _build_error_response(
                resolved_conversation_id,
                result_filename,
                "STT 결과에 document_id로 사용할 id가 없습니다.",
                "stt_document_id_missing",
            )

        # conversation_id가 없으면 현재 사용자 기준 새 채팅방 생성
        # 기존 VOICE_LIBRARY_ROOM_ID는 사용자 소유권 검증이 어려우므로 신규 업로드에는 사용하지 않는다.
        db_conversation_id = resolved_conversation_id or create_conversation(
            title=result_filename or title,
            user_id=user_id,
        )

        stt_json_path = _save_stt_result_to_local_json(
            document_id=document_id,
            content_markdown=content_markdown,
            transcription=transcription,
            metadata=metadata,
            title=result_filename or title,
            summary=summary,
        )

        saved_document_id = save_document_metadata({
            "id": document_id,
            "conversation_id": db_conversation_id,
            "title": result_filename or title,
            "type": "voice",
            "source": "voice",
            "file_path": file_path,
            "json_path": stt_json_path,
            "summary": summary,
            "status": status,
            "notion_url": "",
            "error": error,
            "metadata": json.dumps(metadata, ensure_ascii=False),
        })

        delete_document_chunks(saved_document_id)
        saved_chunk_count = save_document_chunks(
            document_id=saved_document_id,
            transcription=transcription,
        )

        try:
            doc_for_chroma = {
                "id": saved_document_id,
                "document_id": saved_document_id,
                "title": result_filename or title,
                "filename": result_filename or title,
                "type": "voice",
                "source": "voice",
                "transcription": transcription,
                "language": metadata.get("language", "ko"),
                "created_at": "",
                "status": "processed",
                "notion_url": "",
                "error": "",
                "tags": [],
                "importance_score": 0,
            }

            upload_context = _get_upload_context("voice")
            base_meta = _build_base_meta(doc_for_chroma, db_conversation_id)
            base_meta["document_id"] = saved_document_id

            chroma_load_result = _load_voice(doc_for_chroma, base_meta, upload_context)
            chroma_status = (
                "success"
                if chroma_load_result.get("status") == "success"
                else "failed"
            )
            update_chroma_status(saved_document_id, chroma_status)
            print(f"[stt_upload_service] ChromaDB 적재 결과: {chroma_load_result}")

        except Exception as e:
            chroma_status = "failed"
            update_chroma_status(saved_document_id, "failed")
            print(f"[stt_upload_service] ChromaDB 적재 실패: {repr(e)}")

        link_status = "success"
        link_warning = None

        # room_document_links에 연결 추가
        # TODO: CRUD 함수명은 아직 room 기준이므로 추후 conversation 기준 이름으로 변경 예정
        linked = link_document_to_room(
            room_id=db_conversation_id,
            document_id=saved_document_id,
            user_id=user_id,
        )

        if linked:
            print(f"[stt_upload_service] room_document_links 연결 완료: {db_conversation_id} → {saved_document_id}")
        else:
            link_status = "failed"
            link_warning = "음성 문서는 저장되었지만 사건방-문서 연결에 실패했습니다."
            print(f"[stt_upload_service] room_document_links 연결 실패: {db_conversation_id} → {saved_document_id}")

        return _build_success_response(
            conversation_id=db_conversation_id,
            document_id=saved_document_id,
            filename=result_filename,
            title=title,
            file_path=file_path,
            summary=summary,
            saved_chunk_count=saved_chunk_count,
            transcription=transcription,
            metadata=metadata,
            chroma_status=chroma_status,
            link_status=link_status,
            warning=link_warning,
        )

    except PermissionError:
        raise

    except httpx.HTTPStatusError as e:
        return _build_error_response(
            resolved_conversation_id,
            filename,
            "STT 서버 응답 오류가 발생했습니다.",
            str(e),
        )

    except httpx.RequestError as e:
        return _build_error_response(
            resolved_conversation_id,
            filename,
            "STT 서버에 연결할 수 없습니다.",
            str(e),
        )

    except Exception as e:
        return _build_error_response(
            resolved_conversation_id,
            filename,
            "STT 업로드 또는 처리 중 오류가 발생했습니다.",
            str(e),
        )


# STT 목록/상세/삭제

# 전체 음성 목록 조회 (8001 재호출 없이 DB 기준)
def get_stt_list(user_id: str) -> dict:
    try:
        rows = get_voice_documents_for_user(user_id)

        data = []

        for row in rows:
            metadata = _safe_json_loads(row.get("metadata"))
            conversation_id = row.get("conversation_id")

            data.append(
                {
                    "id": row.get("id"),
                    "document_id": row.get("id"),
                    "file_id": _resolve_stt_file_id(row.get("id"), metadata),
                    "room_id": None if _is_voice_library_room_id(conversation_id) else conversation_id,
                    "conversation_id": None if _is_voice_library_room_id(conversation_id) else conversation_id,
                    "title": row.get("title"),
                    "filename": row.get("title"),
                    "type": row.get("type"),
                    "source": row.get("source"),
                    "summary": row.get("summary") or "",
                    "language": metadata.get("language") or "ko",
                    "created_at": row.get("created_at"),
                    "status": row.get("status"),
                    "chroma_status": row.get("chroma_status"),
                    "error": row.get("error"),
                    "duration_sec": _get_duration_sec(metadata),
                    "metadata": metadata,
                }
            )

        return {
            "status": "success",
            "data": data,
            "count": len(data),
            "message": "음성 목록 조회가 완료되었습니다.",
            "error": None,
        }

    except Exception as e:
        print(f"[stt_upload_service] 음성 목록 조회 실패: {repr(e)}")
        return {
            "status": "error",
            "data": [],
            "count": 0,
            "message": "음성 목록 조회 중 오류가 발생했습니다.",
            "error": "stt_list_failed",
        }


# 음성 상세 조회 (DB + document_chunks + 로컬 JSON 기준)
def get_stt_detail(document_id: str, user_id: str) -> dict:
    try:
        document = get_document_by_id_for_user(document_id, user_id)

        if not document:
            raise PermissionError("음성 파일 정보를 찾을 수 없습니다.")

        if document.get("type") != "voice":
            return {
                "status": "error",
                "data": None,
                "message": "요청한 문서는 음성 파일이 아닙니다.",
                "error": "not_voice_document",
            }

        chunks = get_document_chunks(document_id)
        transcription = _chunks_to_transcription(chunks)
        metadata = _safe_json_loads(document.get("metadata"))
        stt_json = _load_stt_json(document.get("json_path") or "")
        conversation_id = document.get("conversation_id")

        return {
            "status": "success",
            "data": {
                "id": document.get("id"),
                "document_id": document.get("id"),
                "file_id": _resolve_stt_file_id(document_id, metadata),
                "room_id": None if _is_voice_library_room_id(conversation_id) else conversation_id,
                "conversation_id": None if _is_voice_library_room_id(conversation_id) else conversation_id,
                "title": document.get("title"),
                "filename": document.get("title"),
                "type": document.get("type"),
                "source": document.get("source"),
                "content": _extract_plain_content_from_json(stt_json),
                "content_markdown": stt_json.get("content_markdown") or "",
                "summary": document.get("summary") or "",
                "language": metadata.get("language") or "ko",
                "created_at": document.get("created_at"),
                "tags": metadata.get("tags") or ["voice_upload"],
                "status": document.get("status"),
                "chroma_status": document.get("chroma_status"),
                "chroma_id": metadata.get("chroma_id"),
                "error": document.get("error"),
                "user_edited": metadata.get("user_edited", False),
                "transcription": transcription,
                "metadata": metadata,
            },
            "message": "음성 상세 조회가 완료되었습니다.",
            "error": None,
        }

    except PermissionError:
        raise

    except Exception as e:
        print(f"[stt_upload_service] 음성 상세 조회 실패: {repr(e)}")
        return {
            "status": "error",
            "data": None,
            "message": "음성 상세 조회 중 오류가 발생했습니다.",
            "error": "stt_detail_failed",
        }


# 음성 삭제 (8001 원본 + ChromaDB 벡터 + 로컬 JSON + DB)
async def delete_stt_document(document_id: str, user_id: str) -> dict:
    try:
        document = get_document_by_id_for_user(document_id, user_id)

        if not document:
            raise PermissionError("음성 파일 정보를 찾을 수 없습니다.")

        if document.get("type") != "voice":
            return {
                "status": "error",
                "document_id": document_id,
                "file_id": None,
                "message": "요청한 문서는 음성 파일이 아닙니다.",
                "error": "not_voice_document",
            }

        metadata = _safe_json_loads(document.get("metadata"))
        file_id = _resolve_stt_file_id(document_id, metadata)
        json_path = document.get("json_path") or ""
        stt_delete_error = None

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.delete(f"{STT_BASE_URL}/api/stt/{file_id}")

            if response.status_code >= 400:
                stt_delete_error = response.text

        except Exception as e:
            stt_delete_error = str(e)

        try:
            chroma_delete_document(document_id)
            print(f"[stt_upload_service] ChromaDB 벡터 삭제 완료: {document_id}")
        except Exception as e:
            print(f"[stt_upload_service] ChromaDB 벡터 삭제 실패: {repr(e)}")

        if json_path:
            try:
                local_path = Path(json_path)
                if local_path.exists() and local_path.is_file():
                    local_path.unlink()
                    print(f"[stt_upload_service] 로컬 JSON 삭제 완료: {json_path}")
            except Exception as e:
                print(f"[stt_upload_service] 로컬 JSON 삭제 실패: {repr(e)}")

        delete_document_chunks(document_id)
        db_deleted = delete_document_for_user(document_id, user_id)

        if stt_delete_error:
            print(f"[stt_upload_service] 8001 원본 파일 삭제 실패: {stt_delete_error}")
            return {
                "status": "partial_success",
                "document_id": document_id,
                "file_id": file_id,
                "message": "8000 DB 데이터는 삭제되었지만, 8001 원본 파일 삭제에 실패했습니다.",
                "error": "stt_original_delete_failed",
            }

        if not db_deleted:
            return {
                "status": "error",
                "document_id": document_id,
                "file_id": file_id,
                "message": "8000 DB 문서 삭제에 실패했습니다.",
                "error": "db_delete_failed",
            }

        return {
            "status": "success",
            "document_id": document_id,
            "file_id": file_id,
            "message": "음성 파일 및 STT 분석 결과가 삭제되었습니다.",
            "error": None,
        }

    except PermissionError:
        raise

    except Exception as e:
        print(f"[stt_upload_service] 음성 삭제 실패: {repr(e)}")
        return {
            "status": "error",
            "document_id": document_id,
            "file_id": None,
            "message": "음성 삭제 중 오류가 발생했습니다.",
            "error": "stt_delete_failed",
        }