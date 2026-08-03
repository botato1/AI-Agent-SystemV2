# backend/services/meeting_service.py

import asyncio
import hashlib
import os
import uuid
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from backend.db.crud import file_crud, meeting_crud, notification_crud, workspace_crud
from backend.db.session import SessionLocal
from backend.modules.rag.document_loader import load_document
from backend.services import judgment_service
from backend.graphs.contradiction_graph import run_contradiction_detection
from backend.graphs.meeting_postprocess_graph import run_meeting_postprocess

MEETING_SUMMARY_STORAGE_DIR = Path("storage/uploads/summaries")

# 완성된 오디오 파일 STT+화자분리 REST 엔드포인트.
# 실시간 녹음(WS, /api/ws/stt/{session_id})과는 별도 경로 — 파일이 이미 통째로 있으므로
# 실시간 스트리밍 프로토콜을 흉내낼 필요 없이 한 번에 전송하고 결과를 받는다.
# ffmpeg 변환(16kHz WAV, 음량정규화)은 서버가 알아서 처리하므로 클라이언트에서 안 해도 됨.
STT_UPLOAD_URL = os.getenv(
    "STT_UPLOAD_URL", "http://61.81.98.82:8002/api/stt"
)
STT_REQUEST_TIMEOUT_SECONDS = 600  # 오디오 길이 비례 GPU 추론 시간 + 화자분리 포함

# 정밀 재분석 결과 조회 (웹훅 수신 후 호출)
STT_SERVER_BASE_URL = os.getenv("STT_SERVER_BASE_URL", "http://61.81.98.82:8002")


def fetch_refined_transcript(stt_meeting_id: str) -> dict:
    """8002의 GET /api/meetings/{id}로 정밀 재분석 결과를 가져온다.

    stt_meeting_id는 8002 자체 형식의 ID(웹훅 payload의 meeting_id)이며,
    우리 Meeting.id(UUID)와는 다르다 - session_id로 우리 회의를 찾은 뒤,
    이 함수엔 웹훅 payload의 meeting_id를 그대로 넘겨야 한다.
    """
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{STT_SERVER_BASE_URL}/api/meetings/{stt_meeting_id}")
    response.raise_for_status()
    return response.json()


async def _request_stt(file_content: bytes, filename: str) -> dict:
    """오디오 파일을 STT REST 서버로 전송하고 STT+화자분리 결과를 받는다."""
    async with httpx.AsyncClient(timeout=STT_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            STT_UPLOAD_URL,
            files={"file": (filename, file_content)},
        )
    response.raise_for_status()
    return response.json()


def _save_segments_bulk(
    meeting_id: uuid.UUID,
    segments: list[dict],
) -> list[tuple[str, str]]:
    """
    worker thread 내부에서 전용 DB Session을 생성해 세그먼트를 저장한다.

    반환 시 ORM 객체를 그대로 넘기지 않고,
    세션 종료 후에도 사용할 수 있는 ID와 content만 반환한다.
    """
    db = SessionLocal()
    try:
        rows = meeting_crud.add_segments_bulk(db, meeting_id, segments)
        return [(str(row.id), row.content or "") for row in rows]
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def _detect_uploaded_audio_contradictions(
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    saved_segments: list[tuple[str, str]],
    meeting_id: uuid.UUID,
    started_by: uuid.UUID,
) -> None:
    """
    업로드 음성에서 생성된 각 발화 세그먼트의 모순 및 판단 파이프라인(결정 리마인더/
    문서 추천/반복논의)을 실행한다.

    다수의 LLM 요청이 한꺼번에 실행되는 것을 막기 위해 순차 처리한다.
    개별 실패는 회의 요약 및 후처리 결과에 영향을 주지 않는다.
    """
    for segment_id, content in saved_segments:
        statement_text = content.strip()
        if not statement_text:
            continue
        try:
            await asyncio.to_thread(
                run_contradiction_detection,
                workspace_id=str(workspace_id),
                category_id=str(category_id),
                source_type="meeting_segment",
                statement_text=statement_text,
                meeting_segment_id=segment_id,
            )
        except Exception as exc:
            print(f"[meeting_service] 모순 감지 실패: segment_id={segment_id}, error={repr(exc)}")

        try:
            await asyncio.to_thread(
                judgment_service.run_judgment_pipeline,
                workspace_id=str(workspace_id),
                category_id=str(category_id),
                source_type="meeting_segment",
                statement_text=statement_text,
                meeting_segment_id=segment_id,
                session_meeting_id=str(meeting_id),
            )
        except Exception as exc:
            print(f"[meeting_service] 판단 파이프라인 실패: segment_id={segment_id}, error={repr(exc)}")


def _mark_failed(db, meeting_id: uuid.UUID) -> None:
    """
    processing 상태인 회의만 failed로 변경한다.

    DB 세션이 오류 상태라면 rollback 후 한 번 더 시도한다.
    상태 변경 실패가 원래 처리 예외를 가리지 않도록 최종 실패는 로그만 남긴다.
    """
    try:
        transitioned = meeting_crud.try_transition_meeting_status(
            db, meeting_id, from_status="processing", to_status="failed",
        )
    except Exception as first_exc:
        db.rollback()
        try:
            transitioned = meeting_crud.try_transition_meeting_status(
                db, meeting_id, from_status="processing", to_status="failed",
            )
        except Exception as retry_exc:
            print(
                f"[meeting_service] meeting_id={meeting_id}를 failed로 변경하지 못했습니다. "
                f"first_error={repr(first_exc)}, retry_error={repr(retry_exc)}"
            )
            return

    if transitioned is None:
        print(f"[meeting_service] meeting_id={meeting_id}는 processing 상태가 아니므로 failed로 변경하지 않습니다.")


async def process_uploaded_audio_stt(
    meeting_id: uuid.UUID,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    file_content: bytes,
) -> None:
    """
    업로드된 음성 파일을 STT REST 서버로 전송한다.

    처리 순서:
    1. created -> processing 상태 전이
    2. STT 서버에 파일 업로드 (변환/화자분리는 서버가 처리)
    3. 발화 세그먼트 일괄 저장
    4. 회의 요약, 결정사항, 할 일 생성
    5. 발화별 모순 감지
    """
    db = SessionLocal()
    try:
        # created -> processing 원자적 전이
        transitioned = meeting_crud.try_transition_meeting_status(
            db, meeting_id, from_status="created", to_status="processing",
        )
        if transitioned is None:
            print(f"[meeting_service] meeting_id={meeting_id}가 created 상태가 아니어서 STT 처리를 시작하지 않습니다.")
            return

        try:
            result = await _request_stt(file_content, f"{meeting_id}.audio")
        except Exception as exc:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            print(f"[meeting_service] STT 서버 요청 실패: {repr(exc)}")
            return

        if result.get("status") != "success":
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            print(f"[meeting_service] STT 처리 실패 응답: {result.get('error') or result.get('message')}")
            return

        transcription = result.get("data", {}).get("transcription") or []
        pending_segments: list[dict] = []
        for segment in transcription:
            try:
                pending_segments.append({
                    "content": segment.get("text", ""),
                    "start_ms": int(segment["start"] * 1000),
                    "end_ms": int(segment["end"] * 1000),
                    "segment_index": len(pending_segments),
                    "speaker_label": segment.get("speaker"),
                })
            except (KeyError, TypeError, ValueError) as exc:
                print(f"[meeting_service] 세그먼트 파싱 실패, 건너뜀: {repr(exc)}")

        if not pending_segments:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            print(f"[meeting_service] STT 결과에 세그먼트가 없습니다: meeting_id={meeting_id}")
            return

        saved_segments = await asyncio.to_thread(_save_segments_bulk, meeting_id, pending_segments)
        if not saved_segments:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            print(f"[meeting_service] 저장된 세그먼트가 없습니다: meeting_id={meeting_id}")
            return

        await asyncio.to_thread(
            run_meeting_postprocess,
            meeting_id=str(meeting_id),
            workspace_id=str(workspace_id),
            category_id=str(category_id),
        )

        await _detect_uploaded_audio_contradictions(
            workspace_id, category_id, saved_segments, meeting_id, transitioned.started_by,
        )
    except Exception as exc:
        _mark_failed(db, meeting_id)
        print(f"[meeting_service] 음성 파일 STT 처리 중 예외 발생: {repr(exc)}")

    finally:
        db.close()

def save_summary_as_document(
    db: Session,
    *,
    meeting_id: uuid.UUID,
    workspace_id: uuid.UUID,
    category_id: uuid.UUID,
    uploaded_by: uuid.UUID,
    title: str,
    full_summary: str,
    short_summary: str,
    discussion_points: list[str],
):
    """회의 요약을 마크다운 문서로 저장하고 workspace_files에 등록한 뒤
    청킹+임베딩(ChromaDB)까지 마치고 meeting_summaries에 연결한다.

    부가 기능이라 실패해도 예외를 밖으로 던지지 않는다 — 이미 저장된 요약/결정사항/할일까지
    실패 처리되는 걸 막기 위함. 실패 시 None을 반환하고 로그만 남긴다.
    """
    try:
        content = (
            f"# {title} 회의 요약\n\n"
            f"## 전체 요약\n{full_summary}\n\n"
            f"## 핵심 요약\n{short_summary}\n\n"
            f"## 논의 사항\n" + "\n".join(f"- {point}" for point in discussion_points)
        )
        content_bytes = content.encode("utf-8")

        MEETING_SUMMARY_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{meeting_id}.md"
        storage_path = MEETING_SUMMARY_STORAGE_DIR / stored_filename
        storage_path.write_bytes(content_bytes)

        workspace_file = file_crud.create_workspace_file(
            db,
            workspace_id=workspace_id,
            category_id=category_id,
            uploaded_by=uploaded_by,
            original_filename=f"{title}_요약.md",
            stored_filename=stored_filename,
            storage_path=str(storage_path),
            mime_type="text/markdown",
            extension="md",
            file_kind="document",
            origin_type="meeting_summary",
            file_size_bytes=len(content_bytes),
            sha256_hash=hashlib.sha256(content_bytes).hexdigest(),
            version_group_id=uuid.uuid4(),
            analysis_status="pending",
        )

        chunks = [
            {"style": "title", "content": f"{title} 회의 요약", "page_number": 1},
            {"style": "heading", "content": "전체 요약", "page_number": 1},
            {"style": "body", "content": full_summary, "page_number": 1},
            {"style": "heading", "content": "핵심 요약", "page_number": 1},
            {"style": "body", "content": short_summary, "page_number": 1},
            {"style": "heading", "content": "논의 사항", "page_number": 1},
            {"style": "body", "content": "\n".join(f"- {p}" for p in discussion_points), "page_number": 1},
        ]
        load_result = load_document(db, workspace_file.id, chunks=chunks)
        if load_result.get("status") == "success":
            file_crud.update_analysis_status(db, workspace_file.id, "completed")
        else:
            file_crud.update_analysis_status(db, workspace_file.id, "failed", error=str(load_result))
            print(f"[meeting_service] 요약 문서 임베딩 실패 (meeting_id={meeting_id}): {load_result}")

        meeting_crud.update_summary_file(db, meeting_id, workspace_file.id)
        return workspace_file

    except Exception as exc:
        db.rollback()
        print(f"[meeting_service] 요약 문서 저장 실패 (meeting_id={meeting_id}): {repr(exc)}")
        return None
    
def run_meeting_postprocess_and_notify(*, meeting_id: str, workspace_id: str, category_id: str) -> None:
    """run_meeting_postprocess 실행 후 완료되면 요약을 문서로 저장하고 워크스페이스 멤버에게 알림."""
    result = run_meeting_postprocess(
        meeting_id=meeting_id, workspace_id=workspace_id, category_id=category_id,
    )
    if result.get("summary_generation_status") != "completed":
        return

    db = SessionLocal()
    try:
        meeting = meeting_crud.get_meeting(db, uuid.UUID(meeting_id))
        title = meeting.title if meeting else "회의"

        if meeting:
            save_summary_as_document(
                db,
                meeting_id=meeting.id,
                workspace_id=meeting.workspace_id,
                category_id=meeting.category_id,
                uploaded_by=meeting.started_by,
                title=title,
                full_summary=result.get("full_summary", ""),
                short_summary=result.get("short_summary", ""),
                discussion_points=result.get("discussion_points", []),
            )

        for member, _user in workspace_crud.list_members(db, uuid.UUID(workspace_id)):
            if not notification_crud.is_notification_enabled(
                db, uuid.UUID(workspace_id), member.user_id, "meeting_summary_ready",
            ):
                continue
            notification_crud.create_notification(
                db, user_id=member.user_id, workspace_id=uuid.UUID(workspace_id),
                type="meeting_summary_ready", title="회의 요약 완료",
                message=f"'{title}' 회의 요약이 준비됐습니다.",
                ref_type="meeting", ref_id=uuid.UUID(meeting_id),
            )
    finally:
        db.close()