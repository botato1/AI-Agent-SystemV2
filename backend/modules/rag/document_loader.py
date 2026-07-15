# backend/modules/rag/document_loader.py
#
# [수정 사항 - 2026.07.14] Re:Call v2 마이그레이션
# 기존 구조: SQLite documents 테이블(json_path, conversation_id)을 조회해서
#            ChromaDB에만 저장 — Postgres 쪽에 아무 row도 안 남았음.
# 변경 구조: workspace_files(file_id)를 기준으로, OCR/STT 결과(chunks[] 또는
#            transcription[])를 인자로 직접 받아서 청킹 후
#              1) ChromaDB에 임베딩 저장 (chroma_client.insert_document)
#              2) Postgres content_chunks에 메타데이터 row 저장 (content_chunk_crud)
#            두 저장을 항상 짝지어 수행함 (doc5 스키마 원칙 #11).
#
# workspace_id/category_id는 더 이상 호출부에서 따로 안 넘겨도 됨 —
# file_id로 workspace_files를 조회해서 자동으로 가져옴 (단일 출처 원칙).
#
# [청킹 전략 — 기존과 동일, 알고리즘 자체는 스키마 무관이라 그대로 유지]
# document 계열 (chunks[] 입력):
#   - style=="caption" 제거 (호출부에서 미리 제거해서 넘겨줄 예정, 방어 코드로 유지)
#   - style=="title"  → 새 청크 경계 + content 맨 앞에 포함
#   - style=="body"   → 500~1700자 기준으로 묶기
#   - content_chunks.chunk_type = "document_text"
#
# meeting/voice 계열 (transcription[] 입력):
#   - 발화를 300~800자 기준으로 묶기, 화자 바뀌는 지점 우선 경계로
#   - content_chunks.chunk_type = "meeting_segment"
#     (주의: 실시간 STT 원본은 meeting_segments 테이블에 발화 단위로 이미 저장됨.
#      여기서 만드는 chunk_type='meeting_segment'는 그것과 다른 개념으로,
#      "RAG 검색에 적합한 크기로 재구성한 회의 전사 청크"를 의미함.
#      이름이 헷갈릴 수 있어 팀 컨벤션 확정되면 chunk_type 값 재검토 필요.)

import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parents[3]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from backend.modules.rag.chroma_client import insert_document, delete_document
from backend.db.crud import content_chunk_crud, file_crud

# ── 청킹 파라미터 ──────────────────────────────────────────────
DOC_CHUNK_MIN  = 500    # 문서 청크 최소 글자 수
DOC_CHUNK_MAX  = 1700   # 문서 청크 최대 글자 수
STT_CHUNK_MIN  = 300    # 음성 청크 최소 글자 수
STT_CHUNK_MAX  = 800    # 음성 청크 최대 글자 수


# ── 문서/회의록 청킹 (스키마 무관, 기존 로직 그대로) ────────────

def _chunk_document(chunks: list) -> list[dict]:
    """
    document/meeting 타입의 chunks[]를 받아서
    검색에 적합한 크기(500~1700자)의 청크 리스트로 반환한다.

    규칙:
    - style == "caption" → 제외 (호출부에서 미리 제거 예정이지만 방어 코드로 유지)
    - style == "title"   → 새 청크 경계. 현재 모인 body가 있으면 먼저 확정.
                           다음 청크의 맨 앞에 이 title을 포함시킴.
    - style == "body"    → 현재 청크에 계속 추가.
                           DOC_CHUNK_MAX를 넘으면 현재 청크 확정 후 새로 시작.

    반환: [{"content": str, "page_number": int}, ...]
    """
    result = []
    current_lines = []
    current_title = ""
    current_page = 1
    current_chars = 0

    def flush(lines, title, page):
        if not lines:
            return
        content = "\n".join(lines).strip()
        if not content:
            return
        if title:
            content = f"{title}\n{content}"
        result.append({"content": content, "page_number": page})

    for chunk in chunks:
        style = (
            chunk.get("metadata", {}).get("style")
            or chunk.get("style")
            or "body"
        )
        content = (
            chunk.get("content")
            or chunk.get("text")
            or ""
        ).strip()
        page = chunk.get("page_number", 1)

        if not content:
            continue
        if style == "caption":
            continue

        if style == "title":
            if current_lines:
                flush(current_lines, current_title, current_page)
                current_lines = []
                current_chars = 0
            current_title = content
            current_page = page

        elif style == "body":
            content_len = len(content)
            if current_chars + content_len > DOC_CHUNK_MAX and current_chars >= DOC_CHUNK_MIN:
                flush(current_lines, current_title, current_page)
                current_lines = []
                current_chars = 0

            current_lines.append(content)
            current_chars += content_len
            current_page = page

    flush(current_lines, current_title, current_page)
    return result


# ── 음성(STT) 청킹 (스키마 무관, 기존 로직 그대로) ──────────────

def _chunk_transcription(transcription: list) -> list[dict]:
    """
    voice 타입의 transcription[]을 받아서
    검색에 적합한 크기(300~800자)의 청크 리스트로 반환한다.

    반환: [{"content": str, "start": float, "end": float}, ...]
    """
    result = []
    current_lines = []
    current_chars = 0
    current_start = 0.0
    current_end = 0.0
    prev_speaker = None

    def flush(lines, start, end):
        if not lines:
            return
        content = "\n".join(lines).strip()
        if content:
            result.append({"content": content, "start": start, "end": end})

    for seg in transcription:
        speaker = seg.get("speaker", "SPEAKER_00")
        text = seg.get("text", "").strip()
        start = seg.get("start", 0.0)
        end = seg.get("end", 0.0)

        if not text:
            continue

        line = f"[{speaker}]: {text}"
        line_len = len(line)

        speaker_changed = (prev_speaker is not None and speaker != prev_speaker)
        over_max = (current_chars + line_len > STT_CHUNK_MAX and current_chars >= STT_CHUNK_MIN)

        if (speaker_changed or over_max) and current_lines:
            flush(current_lines, current_start, current_end)
            current_lines = []
            current_chars = 0
            current_start = start

        if not current_lines:
            current_start = start

        current_lines.append(line)
        current_chars += line_len
        current_end = end
        prev_speaker = speaker

    flush(current_lines, current_start, current_end)
    return result


# ── 메인 적재 함수 ────────────────────────────────────────────

def load_document(
    db: Session,
    file_id: UUID,
    *,
    chunks: Optional[list] = None,
    transcription: Optional[list] = None,
) -> dict:
    """
    workspace_files.id(file_id)를 기준으로 OCR/STT 결과를 청킹하여
    ChromaDB + Postgres(content_chunks)에 동시 저장한다.

    chunks와 transcription 중 정확히 하나만 넘겨야 한다.
    - chunks: OCR 서버가 뽑은 [{"style": "title"|"body"|"caption", "content"/"text": str, "page_number": int}, ...]
    - transcription: STT 서버가 뽑은 [{"speaker": str, "text": str, "start": float, "end": float}, ...]

    workspace_id/category_id는 file_id로 workspace_files를 조회해서 자동으로 가져온다.

    Returns:
        {"status": "success"/"error", "chunk_count": int, "file_id": str, "error": str}
    """
    print(f"[document_loader] 적재 시작 → file_id={file_id}")

    if bool(chunks) == bool(transcription):
        return {
            "status": "error", "chunk_count": 0, "file_id": str(file_id),
            "error": "chunks 또는 transcription 중 정확히 하나만 전달해야 합니다.",
        }

    # 1. workspace_files 조회 → workspace_id/category_id 단일 출처로 가져옴
    file_row = file_crud.get_file(db, file_id)
    if not file_row:
        print(f"[document_loader] file_id를 찾을 수 없음: {file_id}")
        return {"status": "error", "chunk_count": 0, "file_id": str(file_id), "error": "file_not_found"}

    workspace_id = str(file_row.workspace_id)
    category_id = str(file_row.category_id)

    # 2. 청킹
    if transcription is not None:
        if not transcription:
            return {"status": "error", "chunk_count": 0, "file_id": str(file_id), "error": "transcription_empty"}
        chunked = _chunk_transcription(transcription)
        chunk_type = "meeting_segment"
        upload_context = "meeting"
    else:
        if not chunks:
            return {"status": "error", "chunk_count": 0, "file_id": str(file_id), "error": "chunks_empty"}
        chunked = _chunk_document(chunks)
        chunk_type = "document_text"
        upload_context = "document"

    if not chunked:
        print(f"[document_loader] 청킹 결과 없음 → file_id: {file_id}")
        return {"status": "error", "chunk_count": 0, "file_id": str(file_id), "error": "chunk_result_empty"}

    # 3. ChromaDB + Postgres 저장
    #
    # [수정 사항 - 2026.07.15] 리뷰 피드백 반영: 트랜잭션 미분리 문제
    # 기존에는 청크마다 insert_document() → content_chunk_crud.create_chunk()를
    # 반복 호출해서, create_chunk 내부의 개별 commit이 청크 수만큼 발생했음.
    # 중간에 실패하면 ChromaDB엔 있는데 Postgres엔 없는 고아 청크가 생김.
    #
    # 변경: 1) ChromaDB 저장을 먼저 전부 수행하면서 Postgres에 넣을 dict만 모아둠
    #       2) 마지막에 bulk_create_chunks()로 Postgres에 단 한 번만 commit
    #       3) 2번이 실패하면 1번에서 이미 넣은 ChromaDB 청크를 보정 삭제(delete_document)
    #          해서 "ChromaDB엔 있는데 Postgres엔 없는" 상태를 남기지 않음
    chroma_inserted_ids: list[str] = []
    pg_chunk_rows: list[dict] = []

    try:
        for idx, chunk in enumerate(chunked):
            chroma_id = f"{file_id}_chunk_{idx:04d}"

            extra_meta = {}
            if transcription is not None:
                extra_meta = {"stt_start": chunk.get("start", 0.0), "stt_end": chunk.get("end", 0.0)}

            # 3-1. ChromaDB
            insert_document({
                "id": chroma_id,
                "content": chunk["content"],
                "workspace_id": workspace_id,
                "category_id": category_id,
                "document_id": str(file_id),
                "chunk_index": idx,
                "upload_context": upload_context,
                "title": file_row.original_filename,
                "filename": file_row.original_filename,
                **extra_meta,
            })
            chroma_inserted_ids.append(chroma_id)

            # 3-2. Postgres에 넣을 값은 일단 리스트에만 모아둠 (커밋은 아래서 한 번에)
            pg_chunk_rows.append(dict(
                workspace_id=file_row.workspace_id,
                category_id=file_row.category_id,
                file_id=file_id,
                chunk_type=chunk_type,
                chunk_index=idx,
                chunk_text=chunk["content"],
                chroma_id=chroma_id,
                page_number=chunk.get("page_number") if transcription is None else None,
                metadata_json=extra_meta or None,
            ))

        # 3-3. Postgres 단일 트랜잭션으로 일괄 저장
        content_chunk_crud.bulk_create_chunks(db, pg_chunk_rows)
        saved = len(pg_chunk_rows)

    except Exception as e:
        # Postgres 저장(또는 그 이전 단계)이 실패하면, 이미 ChromaDB에 들어간
        # 청크를 보정 삭제해서 고아 데이터를 남기지 않는다.
        print(f"[document_loader] 저장 실패, ChromaDB 보정 삭제 시도: {e}")
        try:
            delete_document(str(file_id), workspace_id)
        except Exception as cleanup_error:
            print(f"[document_loader] 보정 삭제도 실패 — 수동 확인 필요: {cleanup_error}")
        return {"status": "error", "chunk_count": 0, "file_id": str(file_id), "error": str(e)}

    print(f"[document_loader] 완료 → {saved}개 청크 적재 (file_id: {file_id})")
    return {"status": "success", "chunk_count": saved, "file_id": str(file_id), "error": None}