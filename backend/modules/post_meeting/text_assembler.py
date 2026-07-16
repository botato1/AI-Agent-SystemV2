"""post-meeting 파이프라인 2-1: 텍스트 확보

실시간 회의(meeting_segments 이어붙이기) / 회의록 문서 업로드(텍스트 그대로),
두 경로를 하나의 인터페이스로 통일한다.
"""

from sqlalchemy.orm import Session

from backend.db.modules import Meeting, MeetingSegment


def assemble_transcript(db: Session, meeting: Meeting, uploaded_text: str | None = None) -> str:
    """
    meeting.input_type에 따라 전체 텍스트를 확보한다.

    - live_recording / audio_upload: meeting_segments를 segment_index 순으로 이어붙임
    - document_upload: uploaded_text를 그대로 사용 (STT/이어붙이기 불필요)

    반환된 텍스트는 그대로 meeting_summaries.full_transcript에 저장하고,
    llm_extractor.extract()의 입력으로 사용한다.
    """
    if meeting.input_type == "document_upload":
        if not uploaded_text:
            raise ValueError(
                "input_type='document_upload'인 회의는 uploaded_text가 필수입니다."
            )
        return uploaded_text.strip()

    # live_recording / audio_upload
    segments = (
        db.query(MeetingSegment)
        .filter(MeetingSegment.meeting_id == meeting.id)
        .order_by(MeetingSegment.segment_index)
        .all()
    )
    if not segments:
        raise ValueError(f"meeting_id={meeting.id}에 저장된 발화가 없습니다.")

    lines = []
    for seg in segments:
        speaker = seg.speaker_label or "SPEAKER_00"
        lines.append(f"[{speaker}]: {seg.content}")

    return "\n".join(lines)