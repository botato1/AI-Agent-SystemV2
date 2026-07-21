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


def get_segments_for_indexing(
    db: Session, meeting: Meeting, uploaded_text: str | None = None
) -> list[dict]:
    """
    [추가 - 리뷰 반영] 검색용 인덱싱(indexer.index_transcript)에 넘길 구조화된
    발화 리스트를 만든다. assemble_transcript()는 LLM 프롬프트/full_transcript
    저장용으로 발화를 평문 텍스트 하나로 합치면서 타임스탬프를 버리는데, 이걸
    indexer가 다시 줄 단위로 쪼개 start=end=0.0으로 채우면 MeetingSegment의
    실제 start_ms/end_ms가 완전히 유실되는 문제가 있었다 (회의 원문 위치 이동,
    타임스탬프 기반 근거 표시가 불가능해짐).

    이 함수는 평문으로 합치지 않고, MeetingSegment에서 곧바로 구조화된
    리스트(초 단위 타임스탬프 포함)를 만들어 document_loader.load_document()에
    바로 넘길 수 있게 한다.
    """
    if meeting.input_type == "document_upload":
        if not uploaded_text:
            raise ValueError(
                "input_type='document_upload'인 회의는 uploaded_text가 필수입니다."
            )
        # 원본 자체에 타임스탬프가 없으므로 0.0으로 둘 수밖에 없음 (정보 손실이 아니라
        # 애초에 존재하지 않는 정보) - live_recording/audio_upload와는 성격이 다름
        return [{"speaker": "SPEAKER_00", "text": uploaded_text.strip(), "start": 0.0, "end": 0.0}]

    segments = (
        db.query(MeetingSegment)
        .filter(MeetingSegment.meeting_id == meeting.id)
        .order_by(MeetingSegment.segment_index)
        .all()
    )
    if not segments:
        raise ValueError(f"meeting_id={meeting.id}에 저장된 발화가 없습니다.")

    return [
        {
            "speaker": seg.speaker_label or "SPEAKER_00",
            "text": seg.content,
            "start": seg.start_ms / 1000.0,  # ms -> s, document_loader 기존 규격에 맞춤
            "end": seg.end_ms / 1000.0,
        }
        for seg in segments
    ]