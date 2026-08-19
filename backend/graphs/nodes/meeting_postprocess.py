# backend/graphs/nodes/meeting_postprocess.py

# 회의가 끝난(status="processing") 뒤 실행하는 후처리 노드.
# 발화 세그먼트 청킹+임베딩 -> 회의 요약 생성 -> 결정사항/할 일 추출 -> 저장까지 한 번에 처리한다.
#
# 라이브 녹음(input_type="live_recording")은 meeting.source_file_id가 비어있으므로,
# meeting_ws_router.py가 저장해둔 .pcm 파일을 workspace_files에 등록하는 것부터 시작한다.
# audio_upload는 이미 source_file_id가 있다고 가정한다 (실제 STT 실행 연동은 별도 후속 작업).

import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.db.crud import content_chunk_crud, file_crud, meeting_crud
from backend.db.session import SessionLocal
from backend.graphs.states.meeting_postprocess_state import MeetingPostprocessState
from backend.modules.post_meeting import decision_transition, indexer, llm_extractor
from backend.modules.rag.document_loader import load_document

RECORDING_STORAGE_DIR = Path("storage/uploads/recordings")


class _PostprocessFailure(Exception):
    """meeting.status를 failed로 남기고 종료해야 하는 예상된 실패."""


def _parse_due_date(due_date_str: str | None):
    """llm_extractor가 뽑은 'YYYY-MM-DD' 문자열을 datetime으로 변환. 실패하면 None(마감일 없음 취급)."""
    if not due_date_str:
        return None
    try:
        return datetime.strptime(due_date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


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
        # LLM 전용 — 발화 번호를 붙여야 chit_chat_segment_indexes를 세그먼트와 매칭 가능.
        indexed_transcript = "\n".join(
            f"[{s.segment_index}][{s.speaker_label or 'unknown'}] {s.content}" for s in segments
        )

        # 1. 원본 파일 확보 (라이브 녹음이면 새로 등록)
        file_id = _ensure_source_file(db, meeting)

        # 2. 요약 + 결정사항 + 할 일 + 제목 + 잡담 세그먼트 판별 — LLM 호출 한 번에 통합 추출.
        #    (기존엔 이 노드가 자체 프롬프트로 요약/추출을 따로 호출했는데, 승주가 이미
        #    설계해둔 llm_extractor.extract()와 별개로 돌고 있었음 - 여기로 통합)
        #    dict가 아닌 topic/action_item 방어는 extract() 내부(status 검증 루프 이전)에서
        #    처리한다 - 지수 리뷰 반영: 여기서 필터링하면 이미 extract() 내부에서 먼저
        #    죽은 뒤라 아무 소용이 없었음.
        #    잡담 세그먼트를 걸러서 임베딩하려면 임베딩(3번)보다 먼저 호출해야 한다.
        # [추가 - 라이브 테스트 발견] "이번 주 금요일" 같은 상대적 날짜 표현을 LLM이
        # 정확히 절대 날짜로 환산할 수 있게 회의 날짜를 같이 넘긴다 - started_at이
        # 없는 경우(예: 문서 업로드형)는 created_at으로 대체.
        extraction = llm_extractor.extract(
            indexed_transcript, meeting_date=meeting.started_at or meeting.created_at,
        )

        # title_is_auto가 아직 develop에 없을 수 있어(PR #74 미병합) getattr로 방어 —
        # 없으면 기본값 False로 취급해 사용자가 직접 넣은 제목을 절대 덮어쓰지 않는다.
        if extraction.get("title") and getattr(meeting, "title_is_auto", False):
            meeting.title = extraction["title"][:200]

        # 3. 발화 세그먼트 청킹 + 임베딩 (ChromaDB + content_chunks) — 잡담 세그먼트는 제외.
        chit_chat_indexes = set(extraction.get("chit_chat_segment_indexes", []))
        segments_to_index = [s for s in segments if s.segment_index not in chit_chat_indexes]
        if not segments_to_index:
            # 전부 잡담으로 잘못 판단된 경우 안전장치 — 아무것도 임베딩 안 하는 것보다 낫다.
            segments_to_index = segments

        load_result = load_document(db, file_id, transcription=[
            {
                "speaker": s.speaker_label or "unknown",
                "text": s.content,
                "start": s.start_ms / 1000,
                "end": s.end_ms / 1000,
            }
            for s in segments_to_index
        ])
        if load_result.get("status") != "success":
            # 임베딩 실패는 회의 전체를 미완료로 취급한다 — 검색이 안 되는 회의를
            # completed로 표시하면 나중에 "왜 검색이 안 되지"로 이어지기 때문.
            raise _PostprocessFailure(f"세그먼트 임베딩 실패: {load_result}")

        file_crud.update_analysis_status(db, file_id, "completed")  # AI Chat 검색 대상에 포함되려면 필요

        segment_chunks = content_chunk_crud.get_chunks_by_file(db, file_id, chunk_type="meeting_segment")
        segment_chunk_ids = [str(c.id) for c in segment_chunks]

        # 4. 요약 / 결정사항 / 할 일 저장 — 원자적 트랜잭션.
        #    기존엔 단계마다(upsert_summary/process_topics/create_task 각각) 즉시 개별
        #    커밋했는데, 그러면 예를 들어 할 일 저장 도중 예외가 나도 이미 저장된
        #    요약/결정사항은 커밋된 채로 남아 meeting.status만 failed가 되고, 재처리
        #    시 결정사항/할일이 중복 생성될 위험이 있었다 (post_meeting/pipeline.py가
        #    이미 이 문제를 해결한 패턴 — commit=False로 쌓았다가 한 번만 커밋).
        #    이 지점 이전 실패는 전부 롤백, 이후엔 확정된 사실로 취급한다.
        summary_row = meeting_crud.upsert_summary(
            db,
            meeting_id,
            full_summary=extraction["full_summary"],
            short_summary=extraction["short_summary"],
            discussion_points=extraction["discussion_points"],
            generation_status="completed" if extraction["full_summary"] else "failed",
            generated_at=datetime.now(timezone.utc),
            commit=False,
        )

        # decision_transition.process_topics()가 확정/재논의/재확인 상태에 따라
        # 기존 decision을 전이시키거나 새로 등록한다 (post_meeting 파이프라인 2-3
        # 설계 재사용 - 여기서 직접 만들지 않는다).
        # llm_extractor가 이미 status 값을 검증해서 채워주지만, process_topics()도
        # 자체적으로 한 번 더 화이트리스트 검증한다 (지수 리뷰 반영 - PR #65).
        topics = [
            d for d in extraction["topics"]
            if str(d.get("title") or "").strip() and str(d.get("decision_text") or "").strip()
        ]
        new_decisions = decision_transition.process_topics(
            db,
            workspace_id=meeting.workspace_id,
            category_id=meeting.category_id,
            meeting_id=meeting_id,
            topics=topics,
            commit=False,
        )

        task_rows = []
        for t in extraction["action_items"]:
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
                assignee_label=str(t.get("assignee") or "") or None,
                description=str(t.get("description") or "") or None,
                due_at=_parse_due_date(t.get("due_date")),
                commit=False,
            )
            task_rows.append(row)

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        decision_ids = [str(d.id) for d in new_decisions]
        task_ids = [str(row.id) for row in task_rows]

        # 5. 검색 인덱싱 — 4번과 별개 단위 (document_loader/index_decisions는 자체
        #    원자성을 보장하므로 4번의 db.commit()과 억지로 묶지 않는다. 4번이 이미
        #    확정된 뒤라 여기서 실패해도 요약/결정/할일 자체는 무효화되지 않는다).
        # 새로 생성된 decision만 DECISION_COLLECTION에 벡터로 저장한다.
        indexer.index_decisions(db, meeting.workspace_id, meeting.category_id, new_decisions)
        # AI Chat이 "왜 그렇게 결정됐어?" 질문에 원문 발화 청크까지 같이 찾아 보여줄 수
        # 있도록, 이 회의의 content_chunks에 새 decision을 태깅한다 (기존엔 죽은
        # pipeline.py만 이 함수를 호출하고 있어서 실제로는 한 번도 안 쓰이고 있었음).
        indexer.tag_chunks_with_decisions(db, file_id, new_decisions, commit=True)

        meeting_crud.update_meeting_status(db, meeting_id, status="completed")

        return {
            "full_transcript": full_transcript,
            "meeting_segment_ids": [str(s.id) for s in segments],
            "segment_chunk_ids": segment_chunk_ids,
            "full_summary": extraction["full_summary"],
            "short_summary": extraction["short_summary"],
            "discussion_points": extraction["discussion_points"],
            "summary_generation_status": "completed" if extraction["full_summary"] else "failed",
            "meeting_summary_id": str(summary_row.id),
            "extracted_decisions": extraction["topics"],
            "decision_ids": decision_ids,
            "extracted_tasks": extraction["action_items"],
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
