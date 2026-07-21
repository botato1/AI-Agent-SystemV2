"""post-meeting 파이프라인 — 전체 오케스트레이션 (진입점)

트리거: 실시간 녹음 종료 버튼 / 사용자 회의록 문서 업로드

1. 텍스트 확보          (text_assembler)
2. 구조화 LLM 호출       (llm_extractor)
3. Decision 상태 전이    (decision_transition)
4. Task 저장
5. 검색용 인덱싱         (indexer)
6. 완료 처리

[수정 - 2026.07.21 리뷰 재반영] 2단계 커밋 구조로 재설계
기존에 commit=False로 미뤄뒀던 요약/결정/할일 변경이, 그 뒤에 실행되는
indexer.index_transcript() -> document_loader.load_document() ->
content_chunk_crud.bulk_create_chunks() 내부의 db.commit() 때문에
같은 Session 안에서 한꺼번에 강제로 커밋되어버리는 문제가 있었다.
즉 "마지막에 한 번만 commit"하려던 설계가 중간의 남의 commit() 때문에
무력화됨 - commit=False만으로는 충분하지 않았음.

해결: 파이프라인을 두 단계로 명확히 나눈다.

  1단계(핵심 데이터, 원자적): 요약 + 결정 + 할일
    -> 전부 commit=False로 쌓았다가 여기서 딱 한 번 commit.
    -> 이 시점 이전에 실패하면 전부 롤백, 이 시점 이후엔 확정된 사실로 취급.

  2단계(검색 인덱싱 + 알림, 1단계와 별개 단위):
    -> content_chunks/ChromaDB 인덱싱은 document_loader가 이미 자체적으로
       원자성을 보장하는 독립 단위(내부 commit + 실패시 ChromaDB 보정삭제)라
       1단계와 억지로 묶지 않는다.
    -> 2단계가 실패해도 1단계(요약/결정/할일)는 이미 확정된 채로 남는다.
       이건 의도된 동작이다 - 검색 인덱싱 실패가 "이미 내려진 결정"
       자체를 무효로 만들 이유는 없음. 대신 meeting.status로 실패를 표시해서
       재처리가 필요함을 알린다.

⚠️ 재실행 시 멱등성 한계: upsert_summary는 이미 upsert라 안전하지만,
   decision_transition.process_topics()와 create_task()는 재실행 시 동일한
   결정/할일이 중복 생성될 수 있다 (기존에도 있던 한계, 이번 수정 범위 밖 -
   후속 작업으로 upsert 또는 "이 meeting에서 이미 처리됨" 체크 추가 필요).
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from backend.db.crud import meeting_crud, notification_crud
from backend.db.modules import Meeting
from backend.modules.post_meeting import decision_transition, indexer, llm_extractor, text_assembler


def _parse_due_date(due_date_str: str | None):
    """LLM이 뽑은 'YYYY-MM-DD' 문자열을 datetime으로 변환. 실패하면 None (마감일 없음 취급)."""
    if not due_date_str:
        return None
    try:
        return datetime.strptime(due_date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def run(
    db: Session,
    meeting_id: uuid.UUID,
    file_id: uuid.UUID,
    uploaded_text: str | None = None,
) -> dict:
    """
    post-meeting 파이프라인 진입점.

    Args:
        meeting_id: 처리할 회의
        file_id: 이 회의 원문을 인덱싱할 때 연결할 workspace_files.id
                 (live_recording/audio_upload는 meeting.source_file_id,
                  document_upload는 업로드된 문서의 workspace_files.id)
        uploaded_text: input_type='document_upload'일 때만 필수

    Returns:
        {"status": "success"/"partial_success"/"error", "meeting_id": str,
         "decision_count": int, "action_item_count": int, "chunk_count": int,
         "error": str|None}
    """
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        return {"status": "error", "meeting_id": str(meeting_id), "error": "meeting_not_found"}

    # ── 1단계: 핵심 데이터 (요약/결정/할일) — 원자적 트랜잭션 ──────────────
    try:
        transcript = text_assembler.assemble_transcript(db, meeting, uploaded_text=uploaded_text)
        segments_for_indexing = text_assembler.get_segments_for_indexing(
            db, meeting, uploaded_text=uploaded_text
        )

        extracted = llm_extractor.extract(transcript)

        meeting_crud.upsert_summary(
            db,
            meeting_id=meeting.id,
            full_summary=extracted["full_summary"],
            short_summary=extracted["short_summary"],
            discussion_points=extracted["discussion_points"],
            full_transcript=transcript,
            generation_status="completed",
            commit=False,
        )

        new_decisions = decision_transition.process_topics(
            db,
            workspace_id=meeting.workspace_id,
            category_id=meeting.category_id,
            meeting_id=meeting.id,
            topics=extracted["topics"],
            commit=False,
        )

        action_item_count = 0
        for item in extracted["action_items"]:
            # ⚠️ meeting_crud.create_task()가 commit 파라미터를 지원하는지,
            # 함수명이 실제 팀 CRUD와 일치하는지 팀원 확인 필요 (미확인 상태로 병합 금지)
            meeting_crud.create_task(
                db,
                workspace_id=meeting.workspace_id,
                category_id=meeting.category_id,
                title=item.get("title", "")[:200],
                meeting_id=meeting.id,
                assignee_label=item.get("assignee"),
                description=item.get("description"),
                due_at=_parse_due_date(item.get("due_date")),
                status="open",
                commit=False,
            )
            action_item_count += 1

        # 1단계 확정 — 여기서만 커밋. 이 지점 이전 실패는 전부 롤백된다.
        db.commit()

    except Exception as e:
        db.rollback()
        meeting.status = "failed"
        db.commit()
        print(f"[post_meeting.pipeline] 1단계(핵심 데이터) 실패 meeting_id={meeting_id}: {e}")
        return {
            "status": "error", "meeting_id": str(meeting_id),
            "decision_count": 0, "action_item_count": 0, "chunk_count": 0,
            "error": str(e),
        }

    # ── 2단계: 검색 인덱싱 + 알림 — 1단계와 별개 단위 ──────────────────────
    # index_transcript는 document_loader.load_document를 호출하는데, 이 함수는
    # 자체적으로 원자성을 보장하는 독립 단위(내부 commit + 실패시 ChromaDB
    # 보정삭제)라 여기서 억지로 commit=False로 묶지 않는다 (상단 docstring 참조).
    try:
        transcript_index_result = indexer.index_transcript(db, file_id, segments_for_indexing)
        indexer.index_decisions(db, meeting.workspace_id, meeting.category_id, new_decisions)
        indexer.tag_chunks_with_decisions(db, file_id, new_decisions, commit=True)

        notification_crud.create_notification(
            db,
            user_id=meeting.started_by,
            workspace_id=meeting.workspace_id,
            type="meeting_summary_ready",
            title="회의 요약이 완료됐습니다",
            message=extracted["short_summary"],
            ref_type="meeting",
            ref_id=meeting.id,
            commit=True,
        )

        meeting.status = "completed"
        db.commit()

        return {
            "status": "success",
            "meeting_id": str(meeting_id),
            "decision_count": len(new_decisions),
            "action_item_count": action_item_count,
            "chunk_count": transcript_index_result.get("chunk_count", 0),
            "error": None,
        }

    except Exception as e:
        # 1단계(요약/결정/할일)는 이미 커밋되어 확정된 상태 - 되돌리지 않는다.
        # 검색 인덱싱만 실패한 것이므로 meeting 상태만 실패로 표시해 재처리가
        # 필요함을 알린다 (재인덱싱 로직은 후속 작업 - 지금은 상태 표시까지만).
        meeting.status = "failed"
        db.commit()
        print(f"[post_meeting.pipeline] 2단계(인덱싱/알림) 실패 meeting_id={meeting_id}: {e}")
        return {
            "status": "partial_success",
            "meeting_id": str(meeting_id),
            "decision_count": len(new_decisions),
            "action_item_count": action_item_count,
            "chunk_count": 0,
            "error": f"핵심 데이터는 저장됨, 검색 인덱싱 실패: {e}",
        }