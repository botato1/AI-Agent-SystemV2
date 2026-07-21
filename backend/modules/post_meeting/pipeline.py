"""post-meeting 파이프라인 — 전체 오케스트레이션 (진입점)

트리거: 실시간 녹음 종료 버튼 / 사용자 회의록 문서 업로드

1. 텍스트 확보          (text_assembler)
2. 구조화 LLM 호출       (llm_extractor)
3. Decision 상태 전이    (decision_transition)
4. Action Items 저장
5. 검색용 인덱싱         (indexer)
6. 완료 처리

[수정 - 2026.07.21 리뷰 반영]
- (8번) 타임스탬프 소실: indexer.index_transcript()에 평문을 재파싱해서 넘기던 것을
  text_assembler.get_segments_for_indexing()이 만든 구조화 리스트(실제 초 단위
  타임스탬프 포함)를 그대로 넘기도록 변경. document_loader.load_document는 그대로 씀.
- (9번) rollback 무효화: 각 CRUD 호출이 내부적으로 즉시 commit()해서 except 블록의
  db.rollback()이 실제로는 아무것도 되돌리지 못했음. 관련 CRUD 함수들에 commit
  옵션을 추가하고, 여기서는 전부 commit=False로 호출한 뒤 성공 시에만 마지막에
  한 번 commit, 실패 시 rollback 한 번으로 이번 파이프라인 실행분 전체를 되돌림.
  (단, document_loader.load_document 내부의 content_chunk 저장은 자체적으로 이미
  commit+실패시 보정삭제 로직을 갖고 있는 독립 단위라 이 범위 밖 - 설계상 허용된
  예외로 남겨둠. indexer.index_transcript가 이 함수를 그대로 호출함)
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
        {"status": "success"/"error", "meeting_id": str, "decision_count": int,
         "action_item_count": int, "chunk_count": int, "error": str|None}
    """
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        return {"status": "error", "meeting_id": str(meeting_id), "error": "meeting_not_found"}

    try:
        # 1. 텍스트 확보 - LLM 프롬프트용(평문)과 인덱싱용(타임스탬프 보존)을 따로 확보
        transcript = text_assembler.assemble_transcript(db, meeting, uploaded_text=uploaded_text)
        segments_for_indexing = text_assembler.get_segments_for_indexing(
            db, meeting, uploaded_text=uploaded_text
        )

        # 2. 구조화 LLM 호출 (통합 1회)
        extracted = llm_extractor.extract(transcript)

        # meeting_summaries 저장 (full_transcript 포함) - commit=False, 마지막에 일괄 커밋
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

        # 3. Decision 상태 전이
        new_decisions = decision_transition.process_topics(
            db,
            workspace_id=meeting.workspace_id,
            category_id=meeting.category_id,
            meeting_id=meeting.id,
            topics=extracted["topics"],
            commit=False,
        )

        # 4. Action Items 저장 (2-2 결과 그대로 - 별도 LLM 호출 없음)
        # [수정 - 리뷰 반영 5번] action_items -> tasks 명명 변경, 팀 CRUD에 맞춤
        action_item_count = 0
        for item in extracted["action_items"]:
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

        # 5. 검색용 인덱싱 (이중 저장)
        # index_transcript는 document_loader.load_document를 그대로 호출하는데,
        # 이 함수는 자체적으로 commit + 실패시 ChromaDB 보정삭제 로직을 갖고 있는
        # 독립 단위라 여기 트랜잭션 범위 밖임 (설계상 허용된 예외, 주석 상단 참조)
        transcript_index_result = indexer.index_transcript(db, file_id, segments_for_indexing)
        indexer.index_decisions(db, meeting.workspace_id, meeting.category_id, new_decisions)
        indexer.tag_chunks_with_decisions(db, file_id, new_decisions, commit=False)

        notification_crud.create_notification(
            db,
            user_id=meeting.started_by,
            workspace_id=meeting.workspace_id,
            type="meeting_summary_ready",
            title="회의 요약이 완료됐습니다",
            message=extracted["short_summary"],
            ref_type="meeting",
            ref_id=meeting.id,
            commit=False,
        )

        # 6. 완료 처리 - 여기서 전체를 한 번에 커밋 (여기까지 온 것 자체가 전부 성공했다는 뜻)
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
        # 여기까지 오면 위 단계들은 전부 flush만 됐지 commit 안 된 상태이므로
        # rollback이 실제로 이번 실행분 전체(요약/결정/할일/청크태깅/알림)를 되돌린다.
        db.rollback()
        meeting.status = "failed"
        db.commit()
        print(f"[post_meeting.pipeline] 실패 meeting_id={meeting_id}: {e}")
        return {
            "status": "error", "meeting_id": str(meeting_id),
            "decision_count": 0, "action_item_count": 0, "chunk_count": 0,
            "error": str(e),
        }