# backend/graphs/nodes/meeting_postprocess.py

# 회의가 끝난(status="processing") 뒤 실행하는 후처리 노드.
# 발화 세그먼트 청킹+임베딩 -> 회의 요약 생성 -> 결정사항/할 일 추출 -> 저장까지 한 번에 처리한다.
#
# 라이브 녹음(input_type="live_recording")은 meeting.source_file_id가 비어있으므로,
# meeting_ws_router.py가 저장해둔 .pcm 파일을 workspace_files에 등록하는 것부터 시작한다.
# audio_upload는 이미 source_file_id가 있다고 가정한다 (실제 STT 실행 연동은 별도 후속 작업).

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from backend.db.crud import content_chunk_crud, file_crud, meeting_crud
from backend.db.session import SessionLocal
from backend.graphs.states.meeting_postprocess_state import MeetingPostprocessState
from backend.modules.rag.document_loader import load_document

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

RECORDING_STORAGE_DIR = Path("data/uploads/recordings")

_SUMMARY_PROMPT = """당신은 팀 회의록을 정리하는 비서입니다. 아래 회의 전문을 읽고 요약하세요.

[회의 전문]
{transcript}

반드시 아래 JSON 형식으로만 답하세요. 다른 설명은 절대 덧붙이지 마세요.

{{
  "full_summary": "회의 전체 내용을 여러 문단으로 정리",
  "short_summary": "핵심만 한 문단으로",
  "discussion_points": ["주요 논의 주제1", "주요 논의 주제2"]
}}"""

_EXTRACT_PROMPT = """당신은 회의에서 결정사항과 할 일을 추출하는 비서입니다. 아래 회의 전문을 읽으세요.

[회의 전문]
{transcript}

"~로 확정하자/~로 가자/~는 OO가 담당하자" 같은 표현을 결정사항으로, 담당자가 명시된 작업을 할 일로 추출하세요.
반드시 아래 JSON 형식으로만 답하세요. 다른 설명은 절대 덧붙이지 마세요.

{{
  "decisions": [
    {{"title": "짧은 제목", "decision_text": "결정 내용", "reason": "결정 이유(없으면 빈 문자열)"}}
  ],
  "tasks": [
    {{"title": "할 일 내용", "assignee_label": "담당자 이름(없으면 빈 문자열)"}}
  ]
}}"""


class _PostprocessFailure(Exception):
    """meeting.status를 failed로 남기고 종료해야 하는 예상된 실패."""


def _call_llm_json(prompt: str, fallback: dict) -> dict:
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"},
            timeout=120.0,
        )
        response.raise_for_status()
        raw_text = response.json().get("response", "").strip()
        parsed = json.loads(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError(f"응답이 JSON 객체가 아님: {parsed!r}")
        return parsed
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"[meeting_postprocess] LLM 호출 실패: {repr(e)}")
        return fallback


def _generate_summary(full_transcript: str) -> dict:
    parsed = _call_llm_json(
        _SUMMARY_PROMPT.format(transcript=full_transcript),
        fallback={"full_summary": "", "short_summary": "", "discussion_points": []},
    )
    return {
        "full_summary": str(parsed.get("full_summary", "")),
        "short_summary": str(parsed.get("short_summary", "")),
        "discussion_points": parsed.get("discussion_points") or [],
    }


def _extract_decisions_and_tasks(full_transcript: str) -> dict:
    parsed = _call_llm_json(
        _EXTRACT_PROMPT.format(transcript=full_transcript),
        fallback={"decisions": [], "tasks": []},
    )
    decisions = parsed.get("decisions")
    tasks = parsed.get("tasks")
    # LLM이 배열 안에 dict가 아닌 값을 섞어 보낼 수 있으므로 여기서 걸러낸다
    # (호출부에서 다시 .get()을 부르면 AttributeError로 노드 전체가 죽는 걸 방지).
    decisions = [d for d in decisions if isinstance(d, dict)] if isinstance(decisions, list) else []
    tasks = [t for t in tasks if isinstance(t, dict)] if isinstance(tasks, list) else []
    return {"decisions": decisions, "tasks": tasks}


def _ensure_source_file(db, meeting) -> uuid.UUID:
    """라이브 녹음이면 .pcm 파일을 workspace_files에 등록하고 meeting에 연결한다.

    audio_upload인데 source_file_id가 없거나, 라이브 녹음인데 실제 파일이
    없으면(0바이트 포함) 처리 자체가 불가능하므로 실패시킨다.
    """
    if meeting.source_file_id:
        return meeting.source_file_id

    if meeting.input_type != "live_recording":
        raise _PostprocessFailure(
            f"input_type={meeting.input_type!r}인데 source_file_id가 없습니다."
        )

    recording_path = RECORDING_STORAGE_DIR / f"{meeting.id}.pcm"
    if not recording_path.exists() or recording_path.stat().st_size == 0:
        raise _PostprocessFailure(f"녹음 파일이 없거나 비어있습니다: {recording_path}")

    workspace_file = file_crud.create_workspace_file(
        db,
        workspace_id=meeting.workspace_id,
        category_id=meeting.category_id,
        uploaded_by=meeting.started_by,
        original_filename=f"{meeting.title}.pcm",
        stored_filename=f"{meeting.id}.pcm",
        storage_path=str(recording_path),
        mime_type="audio/L16",
        extension="pcm",
        file_kind="audio",
        origin_type="live_recording",
        file_size_bytes=recording_path.stat().st_size,
        sha256_hash="",
        version_group_id=uuid.uuid4(),
        analysis_status="processing",
    )
    meeting_crud.update_meeting_status(
        db, meeting.id, status=meeting.status, source_file_id=workspace_file.id,
    )
    return workspace_file.id


def meeting_postprocess_node(state: MeetingPostprocessState) -> dict:
    meeting_id = uuid.UUID(state["meeting_id"])

    db = SessionLocal()
    try:
        meeting = meeting_crud.get_meeting(db, meeting_id)
        if not meeting:
            return {"error": f"meeting_id={meeting_id} 회의를 찾을 수 없습니다."}

        # 재실행/중복 트리거 방지 — processing 상태일 때만 진행.
        # (완료/실패된 회의를 다시 돌리면 결정사항·할 일이 중복 저장됨)
        if meeting.status != "processing":
            return {"error": f"meeting.status={meeting.status!r}라 후처리를 실행할 수 없습니다 (processing만 허용)."}

        # state로 넘어온 workspace_id/category_id가 실제 meeting 소속과 다르면
        # 호출부가 잘못된 워크스페이스 권한으로 이 노드를 부른 것일 수 있으므로 거부.
        if state.get("workspace_id") and state["workspace_id"] != str(meeting.workspace_id):
            return {"error": "state.workspace_id가 meeting.workspace_id와 일치하지 않습니다."}
        if state.get("category_id") and state["category_id"] != str(meeting.category_id):
            return {"error": "state.category_id가 meeting.category_id와 일치하지 않습니다."}

        segments = meeting_crud.get_segments(db, meeting_id)
        if not segments:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
            return {"error": "발화 세그먼트가 없습니다 (STT 결과 없음)."}

        full_transcript = "\n".join(
            f"[{s.speaker_label or 'unknown'}] {s.content}" for s in segments
        )

        # 1. 원본 파일 확보 (라이브 녹음이면 새로 등록)
        file_id = _ensure_source_file(db, meeting)

        # 2. 발화 세그먼트 청킹 + 임베딩 (ChromaDB + content_chunks)
        load_result = load_document(db, file_id, transcription=[
            {
                "speaker": s.speaker_label or "unknown",
                "text": s.content,
                "start": s.start_ms / 1000,
                "end": s.end_ms / 1000,
            }
            for s in segments
        ])
        if load_result.get("status") != "success":
            # 임베딩 실패는 회의 전체를 미완료로 취급한다 — 검색이 안 되는 회의를
            # completed로 표시하면 나중에 "왜 검색이 안 되지"로 이어지기 때문.
            raise _PostprocessFailure(f"세그먼트 임베딩 실패: {load_result}")
        segment_chunks = content_chunk_crud.get_chunks_by_file(db, file_id, chunk_type="meeting_segment")
        segment_chunk_ids = [str(c.id) for c in segment_chunks]

        # 3. 요약 생성 및 저장
        summary_data = _generate_summary(full_transcript)
        summary_row = meeting_crud.upsert_summary(
            db,
            meeting_id,
            full_summary=summary_data["full_summary"],
            short_summary=summary_data["short_summary"],
            discussion_points=summary_data["discussion_points"],
            generation_status="completed" if summary_data["full_summary"] else "failed",
            generated_at=datetime.now(timezone.utc),
        )

        # 4. 결정사항 / 할 일 추출 및 저장
        extraction = _extract_decisions_and_tasks(full_transcript)

        decision_ids: list[str] = []
        for d in extraction["decisions"]:
            title = str(d.get("title") or "").strip()
            decision_text = str(d.get("decision_text") or "").strip()
            if not title or not decision_text:
                continue
            row = meeting_crud.create_decision(
                db,
                workspace_id=meeting.workspace_id,
                meeting_id=meeting_id,
                title=title,
                decision_text=decision_text,
                decided_at=datetime.now(timezone.utc),
                reason=str(d.get("reason") or "") or None,
                status="active",
            )
            decision_ids.append(str(row.id))

        task_ids: list[str] = []
        for t in extraction["tasks"]:
            title = str(t.get("title") or "").strip()
            if not title:
                continue
            row = meeting_crud.create_task(
                db,
                workspace_id=meeting.workspace_id,
                category_id=meeting.category_id,
                title=title,
                meeting_id=meeting_id,
                status="open",
                assignee_label=str(t.get("assignee_label") or "") or None,
            )
            task_ids.append(str(row.id))

        meeting_crud.update_meeting_status(db, meeting_id, status="completed")

        return {
            "full_transcript": full_transcript,
            "meeting_segment_ids": [str(s.id) for s in segments],
            "segment_chunk_ids": segment_chunk_ids,
            "full_summary": summary_data["full_summary"],
            "short_summary": summary_data["short_summary"],
            "discussion_points": summary_data["discussion_points"],
            "summary_generation_status": "completed" if summary_data["full_summary"] else "failed",
            "meeting_summary_id": str(summary_row.id),
            "extracted_decisions": extraction["decisions"],
            "decision_ids": decision_ids,
            "extracted_tasks": extraction["tasks"],
            "task_ids": task_ids,
        }

    except _PostprocessFailure as e:
        meeting_crud.update_meeting_status(db, meeting_id, status="failed")
        return {"error": str(e)}

    except Exception as e:
        # 예상 못 한 예외로 죽어도 회의가 processing에 영원히 멈춰있지 않도록 failed 처리.
        print(f"[meeting_postprocess] 처리 중 예외 발생: {repr(e)}")
        try:
            meeting_crud.update_meeting_status(db, meeting_id, status="failed")
        except Exception:
            pass
        return {"error": f"후처리 중 예외 발생: {repr(e)}"}

    finally:
        db.close()
