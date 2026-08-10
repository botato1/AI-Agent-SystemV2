# backend/modules/post_meeting/test_decision_transition.py

from backend.modules.post_meeting.decision_transition import process_topics


class _FakeDB:
    """process_topics()가 status 검증에서 걸러 아무 것도 안 건드리는 경로만
    확인하는 테스트용 — DECISION_COLLECTION 검색/LLM 비교까지 갈 일이 없으므로
    flush()만 지원하면 충분하다."""

    def flush(self):
        pass


def test_process_topics_skips_invalid_status():
    topics = [{"title": "제목", "decision_text": "내용", "status": "이상한값"}]
    result = process_topics(
        _FakeDB(), workspace_id="ws", category_id="cat", meeting_id="meeting",
        topics=topics, commit=False,
    )
    assert result == []


def test_process_topics_skips_missing_status():
    topics = [{"title": "제목", "decision_text": "내용"}]  # status 키 자체가 없음
    result = process_topics(
        _FakeDB(), workspace_id="ws", category_id="cat", meeting_id="meeting",
        topics=topics, commit=False,
    )
    assert result == []


def test_process_topics_skips_wrong_case_status():
    topics = [{"title": "제목", "decision_text": "내용", "status": "Confirmed"}]  # 대소문자 다름
    result = process_topics(
        _FakeDB(), workspace_id="ws", category_id="cat", meeting_id="meeting",
        topics=topics, commit=False,
    )
    assert result == []
