"""post-meeting 파이프라인 1: 텍스트 확보

meeting.input_type에 따라 회의 원문을 조립한다.
- live_recording / audio_upload: meeting_segments 테이블의 화자별 발화를 조회해서 합침
- document_upload: 호출부가 넘겨준 uploaded_text를 그대로 사용 (화자 라벨 없음)
"""

from sqlalchemy.orm import Session

from backend.db.crud import meeting_crud
from backend.db.modules import Meeting


def assemble_transcript(db: Session, meeting: Meeting, *, uploaded_text: str | None = None) -> str:
    """llm_extractor에 넘길 전체 원문 텍스트를 조립한다.

    [수정 - 화자 귀속 요약 지원] 발화 번호([번호])만 붙이고 화자 라벨은 안 붙이고
    있었는데, llm_extractor.EXTRACTION_PROMPT_TEMPLATE은 애초에 "각 발화 앞에
    [번호] 형식의 발화 번호가 붙어있다"고 전제하고 chit_chat_segment_indexes를
    뽑고 있어서 번호 자체가 없으면 그 기능이 안 맞았다. 번호와 화자 라벨을
    같이 붙여서 두 문제를 한 번에 해결한다 - 요약이 "누가 말했는지"까지
    포함할 수 있게 됨.
    """
    if meeting.input_type == "document_upload":
        if not uploaded_text:
            raise ValueError("document_upload 회의는 uploaded_text가 필요합니다.")
        return uploaded_text

    segments = meeting_crud.get_segments(db, meeting.id)
    return "\n".join(
        f"[{i}][{s.speaker_label or 'SPEAKER'}]: {s.content}"
        for i, s in enumerate(segments)
    )


def get_segments_for_indexing(
    db: Session, meeting: Meeting, *, uploaded_text: str | None = None
) -> list[dict]:
    """document_loader._chunk_transcription()이 기대하는 구조로 변환.

    반환: [{"speaker": str, "text": str, "start": float, "end": float}, ...]
    """
    if meeting.input_type == "document_upload":
        if not uploaded_text:
            raise ValueError("document_upload 회의는 uploaded_text가 필요합니다.")
        return [{"speaker": None, "text": uploaded_text, "start": 0.0, "end": 0.0}]

    segments = meeting_crud.get_segments(db, meeting.id)
    return [
        {
            "speaker": s.speaker_label or "SPEAKER_00",
            "text": s.content,
            "start": s.start_ms / 1000.0,
            "end": s.end_ms / 1000.0,
        }
        for s in segments
    ]
