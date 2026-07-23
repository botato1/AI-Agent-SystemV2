# backend/graphs/test_ai_chat_graph.py

from backend.graphs.nodes.ai_chat_answer import (
    merge_and_rank_candidates,
    format_chat_history,
    build_answer_prompt,
)


def test_merge_and_rank_candidates_orders_by_score():
    doc_results = [{"id": "d1", "score": 0.9}, {"id": "d2", "score": 0.3}]
    meeting_results = [{"id": "m1", "score": 0.95}, {"id": "m2", "score": 0.5}]

    result = merge_and_rank_candidates(doc_results, meeting_results, top_k=3)

    assert [r["id"] for r in result] == ["m1", "d1", "m2"]


def test_merge_and_rank_candidates_empty_inputs():
    assert merge_and_rank_candidates([], [], top_k=5) == []


def test_merge_and_rank_candidates_respects_top_k():
    doc_results = [{"id": f"d{i}", "score": i / 10} for i in range(10)]
    result = merge_and_rank_candidates(doc_results, [], top_k=3)
    assert len(result) == 3
    assert result[0]["id"] == "d9"


def test_format_chat_history_empty():
    assert format_chat_history(None) == "(이전 대화 없음)"
    assert format_chat_history([]) == "(이전 대화 없음)"


def test_format_chat_history_truncates_to_recent_turns():
    history = [
        {"role": "user", "content": f"질문{i}"} if i % 2 == 0 else {"role": "assistant", "content": f"답변{i}"}
        for i in range(10)
    ]
    result = format_chat_history(history, max_turns=2)
    lines = result.split("\n")

    assert len(lines) == 4
    assert "질문8" in result
    assert "질문0" not in result


def test_format_chat_history_labels_roles():
    history = [{"role": "user", "content": "안녕"}, {"role": "assistant", "content": "네 안녕하세요"}]
    result = format_chat_history(history)
    assert "사용자: 안녕" in result
    assert "AI: 네 안녕하세요" in result


def test_build_answer_prompt_includes_context_and_question():
    prompt = build_answer_prompt(["문서 내용 A"], None, "질문입니다")
    assert "문서 내용 A" in prompt
    assert "질문입니다" in prompt
    assert "(이전 대화 없음)" in prompt


def test_build_answer_prompt_empty_context():
    prompt = build_answer_prompt([], None, "질문")
    assert "(근거 자료 없음)" in prompt
