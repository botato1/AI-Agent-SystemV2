# backend/services/meeting_service.py

import asyncio
import hashlib
import os
import uuid
import time
from pathlib import Path
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from backend.db.crud import file_crud, meeting_crud, notification_crud, workspace_crud
from backend.db.session import SessionLocal
from backend.modules.rag.document_loader import load_document
from backend.modules.post_meeting import llm_extractor
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

    주의: 이 함수는 세션 하나(재연결 전/후 중 한쪽)의 세그먼트만 반환한다.
    회의 전체 요약을 만들 땐 fetch_merged_refined_transcript()를 써야 한다.
    """
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{STT_SERVER_BASE_URL}/api/meetings/{stt_meeting_id}")
    response.raise_for_status()
    return response.json()


def fetch_merged_refined_transcript(session_id: str) -> dict:
    """이 회의(session_id)에 속한 모든 STT 세션의 정밀 재분석 세그먼트를 시간순으로 합쳐서 반환한다.

    재연결/재개로 같은 session_id에 STT 서버 쪽 meeting_id가 여러 개 생긴 경우,
    세션 하나의 세그먼트만으로 요약을 만들면 다른 세션 구간이 통째로 빠진다.
    GET /api/meetings 목록에서 이 session_id에 해당하는 세션을 전부 찾아
    시작 시각(started_at) 순으로 세그먼트를 이어붙인다.
    """
    with httpx.Client(timeout=30.0) as client:
        list_response = client.get(f"{STT_SERVER_BASE_URL}/api/meetings")
    list_response.raise_for_status()

    sessions = [
        item for item in list_response.json().get("meetings", [])
        if item.get("session_id") == session_id
    ]
    sessions.sort(key=lambda item: item.get("started_at") or "")

    merged_segments: list[dict] = []
    for item in sessions:
        stt_meeting_id = item.get("meeting_id")
        if not stt_meeting_id:
            continue
        try:
            detail = fetch_refined_transcript(stt_meeting_id)
        except httpx.HTTPError as e:
            print(f"[meeting_service] 세션 세그먼트 조회 실패, 건너뜀: stt_meeting_id={stt_meeting_id}, error={repr(e)}")
            continue
        merged_segments.extend(detail.get("segments", []))

    return {"segments": merged_segments}


async def _request_stt(file_content: bytes, filename: str) -> dict:
    """오디오 파일을 STT REST 서버로 전송하고 STT+화자분리 결과를 받는다."""
    async with httpx.AsyncClient(timeout=STT_REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(
            STT_UPLOAD_URL,
            files={"file": (filename, file_content)},
        )
    response.raise_for_status()
    return response.json()

def regenerate_summary_from_refined_transcript(
    meeting_id: str, refined_data: dict,
    max_wait_seconds: float = 300.0, poll_interval_seconds: float = 5.0,
    force: bool = False,
) -> None:
    """정밀 재분석 완료 웹훅 수신 시 요약만 다시 생성해 갱신한다.

    force=True면 이미 재분석 반영된 회의도 다시 갱신한다 - 사용자가 "재분석"
    버튼으로 수동 재요청한 경우(trigger_manual_reanalysis)에 쓴다. 기본값(False)은
    웹훅 중복 수신 방지용 dedup을 그대로 유지한다.

    meeting_postprocess_node는 재실행하지 않는다 - 그 노드가 결정사항/할 일
    추출까지 한 번에 묶여있어서, 여기서 다시 부르면 decision/task가 중복
    생성될 위험이 있다(가동현 - 웹훅 반영 보류 사유). 대신 llm_extractor.extract()만
    직접 호출해서 요약 관련 필드(full_summary/short_summary/discussion_points/
    meeting_purpose/next_steps)만 갱신하고, topics/action_items는 버린다.

    [수정 - 리뷰 반영] meeting_postprocess_node(백그라운드, 무거움)와 이 함수가
    회의 종료 시점에 동시에 시작되는데, 둘 사이에 순서 보장이 없었다. postprocess가
    이 함수보다 늦게 끝나면, 이 함수가 먼저 써놓은 재분석 기반 요약(+발송된 완료
    알림)을 postprocess가 뒤늦게 실시간본 기준으로 조용히 덮어써버리는 문제가 있었음.
    그래서 이 함수 진입 시 postprocess가 실제로 끝났는지(generation_status가
    completed/failed) 확인하고, 아직 진행 중이면 짧게 재시도하며 기다린다. postprocess가
    끝난 뒤에만 이 함수가 쓰기 때문에, 이후로는 아무도 이 값을 덮어쓰지 않는다.
    """
    db = SessionLocal()
    try:
        meeting_uuid = uuid.UUID(meeting_id)
        waited = 0.0
        while True:
            db.expire_all()
            summary_row = meeting_crud.get_meeting_summary(db, meeting_uuid)
            if summary_row and summary_row.generation_status in ("completed", "failed"):
                break
            if waited >= max_wait_seconds:
                print(
                    f"[meeting_service] meeting_postprocess_node 완료 대기 타임아웃"
                    f"({max_wait_seconds}s), 재분석 요약 갱신 스킵: meeting_id={meeting_id}"
                )
                return
            time.sleep(poll_interval_seconds)
            waited += poll_interval_seconds

        if summary_row.refined_at is not None and not force:
            print(f"[meeting_service] 이미 재분석 반영됨, 중복 웹훅 스킵: meeting_id={meeting_id}")
            return

        segments = refined_data.get("segments", [])
        if not segments:
            print(f"[meeting_service] 재분석 세그먼트 없음, 요약 갱신 스킵: meeting_id={meeting_id}")
            return

        indexed_transcript = "\n".join(
            f"[{i}][{seg.get('speaker') or 'unknown'}] {seg.get('text', '')}"
            for i, seg in enumerate(segments)
        )

        extraction = llm_extractor.extract(indexed_transcript)
        if not extraction.get("full_summary"):
            print(f"[meeting_service] 재분석 요약 생성 실패, 갱신 스킵: meeting_id={meeting_id}")
            return

        meeting = meeting_crud.get_meeting(db, meeting_uuid)
        if not meeting:
            print(f"[meeting_service] 재분석 요약 갱신 대상 회의를 찾을 수 없음: meeting_id={meeting_id}")
            return

        meeting_crud.upsert_summary(
            db,
            meeting_uuid,
            meeting_purpose=extraction["meeting_purpose"],
            full_summary=extraction["full_summary"],
            short_summary=extraction["short_summary"],
            discussion_points=extraction["discussion_points"],
            next_steps=extraction["next_steps"],
            generation_status="completed",
            generated_at=datetime.now(timezone.utc),
            refined_at=datetime.now(timezone.utc),
        )

        # [수정 - 리뷰 반영] create_notification 기본값(commit=True)을 그대로 쓰면
        # 멤버 수만큼 개별 커밋이 일어나서, 중간에 실패하면 일부 멤버만 알림을 받은
        # 채로 남는다. post_meeting/pipeline.py와 동일하게 commit=False로 쌓고
        # 마지막에 한 번만 커밋한다.
        for member, _user in workspace_crud.list_members(db, meeting.workspace_id):
            if not notification_crud.is_notification_enabled(
                db, meeting.workspace_id, member.user_id, "meeting_summary_ready",
            ):
                continue
            notification_crud.create_notification(
                db, user_id=member.user_id, workspace_id=meeting.workspace_id,
                type="meeting_summary_ready", title="회의 요약 개선 완료",
                message=f"'{meeting.title}' 회의 요약이 더 정확한 내용으로 갱신됐습니다.",
                ref_type="meeting", ref_id=meeting.id,
                commit=False,
            )
        db.commit()

        print(f"[meeting_service] 재분석본 기준 요약 갱신 완료: meeting_id={meeting_id}")
    except Exception as e:
        db.rollback()
        print(f"[meeting_service] 재분석본 요약 갱신 실패: meeting_id={meeting_id}, error={repr(e)}")
    finally:
        db.close()


def _find_stt_meeting_id(session_id: str) -> str | None:
    """8002의 GET /api/meetings 목록에서 session_id로 STT 쪽 meeting_id("{session_id}_{timestamp}")를 찾는다.

    우리 Meeting.id(UUID)는 STT 서버 호출 시 session_id로 쓰이지만, STT 서버는
    자기 자신의 meeting_id(파일 경로에 쓰는 조합 ID)를 별도로 갖고 있어서 이걸로
    변환해야 /refine 엔드포인트를 호출할 수 있다.
    """
    with httpx.Client(timeout=30.0) as client:
        response = client.get(f"{STT_SERVER_BASE_URL}/api/meetings")
    response.raise_for_status()
    for item in response.json().get("meetings", []):
        if item.get("session_id") == session_id:
            return item.get("meeting_id")
    return None


def trigger_manual_reanalysis(meeting_id: str, stt_meeting_id: str | None = None) -> None:
    """사용자가 "재분석" 버튼을 눌렀을 때 STT 서버의 정밀 재분석을 수동으로 재요청한다.

    stt_meeting_id는 이 회의가 웹훅을 한 번이라도 받아서 DB(Meeting.stt_meeting_id)에
    저장해둔 값을 우선 사용한다 - session_id 재사용(재연결/재개) 시 STT 서버에 동일
    session_id로 여러 meeting_id가 생길 수 있어 검색만으로는 항상 정확하지 않기 때문이다.
    아직 한 번도 웹훅을 못 받은 회의는(None) session_id 기반 최신순 검색으로 폴백한다.

    force=True로 호출하므로 이미 재분석된 회의도 다시 돌아간다(기존 재분석본 덮어씀,
    실시간 결과는 보존됨 - STT 서버 쪽 정책). 오래 걸리는 GPU 작업이라 백그라운드
    태스크로 실행하고, 끝나면 웹훅 수신 때와 동일한 경로로 요약을 갱신한다.
    """
    try:
        if not stt_meeting_id:
            stt_meeting_id = _find_stt_meeting_id(meeting_id)
        if not stt_meeting_id:
            print(f"[meeting_service] 수동 재분석 대상 없음: STT 서버에 session_id={meeting_id} 회의가 없습니다.")
            return

        with httpx.Client(timeout=STT_REQUEST_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{STT_SERVER_BASE_URL}/api/meetings/{stt_meeting_id}/refine",
                params={"force": "true"},
            )
        response.raise_for_status()
        print(f"[meeting_service] 수동 재분석 완료: meeting_id={meeting_id}, stt_meeting_id={stt_meeting_id}")

        # 세션 하나가 아니라, 이 회의에 속한 모든 세션의 세그먼트를 합쳐서 요약을 만든다
        # (재연결로 세션이 여러 개면 방금 재분석한 세션 구간만으로는 요약이 불완전해진다).
        refined_data = fetch_merged_refined_transcript(meeting_id)
        regenerate_summary_from_refined_transcript(meeting_id=meeting_id, refined_data=refined_data, force=True)
    except Exception as e:
        print(f"[meeting_service] 수동 재분석 실패: meeting_id={meeting_id}, error={repr(e)}")


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
    decisions: list[dict] | None = None,
    action_items: list[dict] | None = None,
):
    """회의 요약을 마크다운 문서로 저장하고 workspace_files에 등록한 뒤
    청킹+임베딩(ChromaDB)까지 마치고 meeting_summaries에 연결한다.

    [수정] decisions/action_items 추가 - llm_extractor가 이미 뽑아둔 결정사항/할일이
    지금까지는 요약 문서에 아예 안 들어가고 있었다(full_summary/short_summary/
    discussion_points만 포함). "회의록"이라 부를 만한 핵심 정보(결정사항/할일)가
    검색 대상에서 빠져있던 것 - 같이 포함시킨다.

    [수정] 이 콘텐츠는 회의에서 나온 것이라 문서 업로드(DOCUMENT_COLLECTION)가 아니라
    회의 컬렉션(MEETING_COLLECTION)에 들어가야 한다 - load_document() 호출 시
    upload_context_override="meeting", chunk_type_override="meeting_summary"로 지정.

    부가 기능이라 실패해도 예외를 밖으로 던지지 않는다 — 이미 저장된 요약/결정사항/할일까지
    실패 처리되는 걸 막기 위함. 실패 시 None을 반환하고 로그만 남긴다.
    """
    try:
        decisions = decisions or []
        action_items = action_items or []

        # [수정 - 리뷰 반영] decisions엔 status="reopened_no_conclusion"(재논의했지만
        # 결론 안 남)인 항목도 섞여 들어온다. decision_text가 이 경우 "확정된 내용"이
        # 아니라 "논의 중이던 내용"이라, 전부 "결정사항"에 넣으면 아직 안 정해진 걸
        # 정해진 것처럼 보여주게 된다. status로 갈라서 별도 섹션으로 분리한다.
        confirmed_decisions = [d for d in decisions if d.get("status") != "reopened_no_conclusion"]
        pending_decisions = [d for d in decisions if d.get("status") == "reopened_no_conclusion"]

        decisions_text = (
            "\n".join(
                f"- **{d.get('title', '')}**: {d.get('decision_text', '')}"
                + (f" (사유: {d['reason']})" if d.get("reason") else "")
                for d in confirmed_decisions
            )
            if confirmed_decisions else "(이번 회의에서 새로 확정된 결정사항 없음)"
        )
        pending_decisions_text = (
            "\n".join(
                f"- **{d.get('title', '')}**: {d.get('decision_text', '')}"
                + (f" (사유: {d['reason']})" if d.get("reason") else "")
                for d in pending_decisions
            )
            if pending_decisions else "(이번 회의에서 결론 안 난 안건 없음)"
        )
        action_items_text = (
            "\n".join(
                f"- {a.get('title', '')}"
                + (f" (담당: {a['assignee']})" if a.get("assignee") else "")
                + (f" (기한: {a['due_date']})" if a.get("due_date") else "")
                for a in action_items
            )
            if action_items else "(이번 회의에서 새로 생성된 할 일 없음)"
        )

        content = (
            f"# {title} 회의 요약\n\n"
            f"## 전체 요약\n{full_summary}\n\n"
            f"## 핵심 요약\n{short_summary}\n\n"
            f"## 논의 사항\n" + "\n".join(f"- {point}" for point in discussion_points) + "\n\n"
            f"## 결정사항\n{decisions_text}\n\n"
            f"## 논의 중/미결 안건\n{pending_decisions_text}\n\n"
            f"## 할 일\n{action_items_text}"
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
            {"style": "heading", "content": "결정사항", "page_number": 1},
            {"style": "body", "content": decisions_text, "page_number": 1},
            {"style": "heading", "content": "논의 중/미결 안건", "page_number": 1},
            {"style": "body", "content": pending_decisions_text, "page_number": 1},
            {"style": "heading", "content": "할 일", "page_number": 1},
            {"style": "body", "content": action_items_text, "page_number": 1},
        ]
        # upload_context_override="meeting" — 이 콘텐츠는 회의에서 나온 것이라
        # DOCUMENT_COLLECTION이 아니라 MEETING_COLLECTION에 들어가야 한다
        # (기존엔 문서 청킹 경로를 그대로 써서 upload_context가 "document"로
        # 고정돼있었음 - 그래서 contradiction_detect 등 문서 전용 소비자가
        # 회의 요약까지 일반 문서로 오인해서 스캔하는 문제가 있었다).
        load_result = load_document(
            db, workspace_file.id, chunks=chunks,
            upload_context_override="meeting", chunk_type_override="meeting_summary",
        )
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
                decisions=result.get("extracted_decisions", []),
                action_items=result.get("extracted_tasks", []),
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