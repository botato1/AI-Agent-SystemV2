# backend/graphs/test_ai_chat_graph.py

from backend.graphs.nodes.ai_chat_answer import (
    candidate_score,
    merge_and_rank_candidates,
    filter_by_relevance,
    clamp_similarity_score,
    format_chat_history,
    build_answer_prompt,
    _parse_cited_indices,
)


def test_merge_and_rank_candidates_orders_by_score():
    """최소 보장을 끄면(min_per_collection=0) 순수 점수순으로 동작한다."""
    doc_results = [{"id": "d1", "score": 0.9}, {"id": "d2", "score": 0.3}]
    meeting_results = [{"id": "m1", "score": 0.95}, {"id": "m2", "score": 0.5}]

    result = merge_and_rank_candidates(
        doc_results, meeting_results, top_k=3, min_per_collection=0
    )

    assert [r["id"] for r in result] == ["m1", "d1", "m2"]


def test_merge_and_rank_candidates_guarantees_minimum_per_collection():
    """한 컬렉션이 상위 점수를 독식해도 다른 컬렉션 후보가 살아남아야 한다."""
    doc_results = [{"id": "d1", "score": 0.30}, {"id": "d2", "score": 0.25}]
    meeting_results = [{"id": f"m{i}", "score": 0.9 - i * 0.01} for i in range(5)]

    result = merge_and_rank_candidates(
        doc_results, meeting_results, top_k=4, min_per_collection=2
    )

    ids = [r["id"] for r in result]
    # 점수만 보면 meeting이 4자리를 다 가져가지만, doc 2개가 보장되어야 한다
    assert "d1" in ids and "d2" in ids
    assert len([i for i in ids if i.startswith("m")]) == 2
    # 반환 순서는 점수순
    assert ids == sorted(ids, key=lambda i: candidate_score(
        next(r for r in result if r["id"] == i)), reverse=True)


def test_merge_and_rank_candidates_quota_exceeds_top_k_distributes_evenly():
    """min_per_collection * 컬렉션수 > top_k면 라운드로빈으로 균등 분배한다."""
    doc_results = [{"id": "d1", "score": 0.1}, {"id": "d2", "score": 0.09}]
    meeting_results = [{"id": "m1", "score": 0.2}, {"id": "m2", "score": 0.19}]
    decision_results = [{"id": "x1", "score": 0.3}, {"id": "x2", "score": 0.29}]

    result = merge_and_rank_candidates(
        doc_results, meeting_results, decision_results, top_k=3, min_per_collection=2
    )

    # 3자리를 한 컬렉션이 독식하지 않고 컬렉션당 1개씩 가져간다
    assert sorted(r["id"] for r in result) == ["d1", "m1", "x1"]


def test_merge_and_rank_candidates_prefers_reranker_score():
    """reranker_score가 있으면 하이브리드 score 대신 그것으로 랭킹한다."""
    doc_results = [{"id": "d1", "score": 0.9, "reranker_score": 0.1}]
    meeting_results = [{"id": "m1", "score": 0.2, "reranker_score": 0.95}]

    result = merge_and_rank_candidates(
        doc_results, meeting_results, top_k=2, min_per_collection=0
    )

    assert [r["id"] for r in result] == ["m1", "d1"]


def test_merge_and_rank_candidates_no_duplicates():
    """보장 단계와 잔여 채움 단계에서 같은 후보가 중복 선택되면 안 된다."""
    doc_results = [{"id": "d1", "score": 0.9}, {"id": "d2", "score": 0.8}]
    meeting_results = [{"id": "m1", "score": 0.7}]

    result = merge_and_rank_candidates(
        doc_results, meeting_results, top_k=5, min_per_collection=2
    )

    ids = [r["id"] for r in result]
    assert sorted(ids) == ["d1", "d2", "m1"]


def test_merge_and_rank_candidates_empty_inputs():
    assert merge_and_rank_candidates([], [], top_k=5) == []


def test_merge_and_rank_candidates_respects_top_k():
    doc_results = [{"id": f"d{i}", "score": i / 10} for i in range(10)]
    result = merge_and_rank_candidates(doc_results, [], top_k=3)
    assert len(result) == 3
    assert result[0]["id"] == "d9"


def test_merge_and_rank_candidates_includes_decision_results():
    doc_results = [{"id": "d1", "score": 0.5}]
    meeting_results = [{"id": "m1", "score": 0.4}]
    decision_results = [{"id": "dec1", "score": 0.9}]

    result = merge_and_rank_candidates(doc_results, meeting_results, decision_results, top_k=3)

    assert [r["id"] for r in result] == ["dec1", "d1", "m1"]


def test_merge_and_rank_candidates_decision_results_optional():
    """decision_results를 생략해도 기존 2종 병합과 동일하게 동작해야 한다 (하위 호환)."""
    doc_results = [{"id": "d1", "score": 0.9}]
    meeting_results = [{"id": "m1", "score": 0.5}]
    result = merge_and_rank_candidates(doc_results, meeting_results, top_k=2)
    assert [r["id"] for r in result] == ["d1", "m1"]


def test_filter_by_relevance_drops_low_score_candidates():
    candidates = [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.2}, {"id": "c", "score": 0.4}]
    result = filter_by_relevance(candidates, min_score=0.4)
    assert [c["id"] for c in result] == ["a", "c"]


def test_filter_by_relevance_empty_when_all_below_threshold():
    candidates = [{"id": "a", "score": 0.1}, {"id": "b", "score": 0.05}]
    assert filter_by_relevance(candidates, min_score=0.4) == []


def test_filter_by_relevance_missing_score_treated_as_zero():
    candidates = [{"id": "a"}]
    assert filter_by_relevance(candidates, min_score=0.4) == []


def test_filter_by_relevance_uses_reranker_score_when_present():
    """리랭킹을 거쳤으면 하이브리드 score가 아니라 reranker_score로 걸러야 한다.

    오타 등으로 BM25 항이 0이 되어 하이브리드 점수가 낮아도, 리랭커가 높게
    평가한 후보는 살아남아야 한다 (지수 리포트: "베포" → "배포" 케이스).
    """
    candidates = [
        {"id": "a", "score": 0.35, "reranker_score": 0.88},
        {"id": "b", "score": 0.95, "reranker_score": 0.10},
    ]
    result = filter_by_relevance(candidates, min_score=0.4)
    assert [c["id"] for c in result] == ["a"]


def test_candidate_score_falls_back_to_hybrid_score():
    """리랭커 미적용/실패로 reranker_score가 없으면 하이브리드 score를 쓴다."""
    assert candidate_score({"score": 0.7}) == 0.7
    assert candidate_score({"score": 0.7, "reranker_score": 0.2}) == 0.2
    assert candidate_score({}) == 0.0


def test_clamp_similarity_score_within_range():
    assert clamp_similarity_score(0.75) == 0.75


def test_clamp_similarity_score_clamps_above_one():
    assert clamp_similarity_score(1.4) == 1.0


def test_clamp_similarity_score_clamps_below_zero():
    assert clamp_similarity_score(-0.3) == 0.0


def test_clamp_similarity_score_handles_none():
    assert clamp_similarity_score(None) == 0.0


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


def test_build_answer_prompt_numbers_context_items():
    """근거마다 [1] [2] 번호가 붙어야 _parse_cited_indices()가 되읽을 수 있다."""
    prompt = build_answer_prompt(["문서 A", "문서 B", "문서 C"], None, "질문")
    assert "[1] 문서 A" in prompt
    assert "[2] 문서 B" in prompt
    assert "[3] 문서 C" in prompt


def test_parse_cited_indices_extracts_numbers():
    answer, indices = _parse_cited_indices("이렇게 답변합니다.\n[출처: 1,3]")
    assert answer == "이렇게 답변합니다."
    assert indices == {1, 3}


def test_parse_cited_indices_handles_spaces_and_duplicates():
    answer, indices = _parse_cited_indices("답변 내용\n[출처: 1, 1, 2]")
    assert answer == "답변 내용"
    assert indices == {1, 2}


def test_parse_cited_indices_no_marker_falls_back_to_none():
    """마커가 아예 없으면 원본 답변 그대로, indices는 None(=호출부가 전체 표시로 폴백)."""
    answer, indices = _parse_cited_indices("그냥 평범한 답변입니다.")
    assert answer == "그냥 평범한 답변입니다."
    assert indices is None


def test_parse_cited_indices_empty_marker_falls_back_to_none():
    """마커는 있는데 숫자가 하나도 없으면(형식 깨짐) 폴백. 마커 텍스트는 그래도 지운다."""
    answer, indices = _parse_cited_indices("답변입니다.\n[출처: ]")
    assert answer == "답변입니다."
    assert indices is None


def test_parse_cited_indices_non_digit_falls_back_to_none():
    answer, indices = _parse_cited_indices("답변입니다.\n[출처: a,b]")
    assert answer == "답변입니다."
    assert indices is None


def test_parse_cited_indices_marker_not_at_end_is_ignored():
    """마커가 맨 끝이 아니면(본문 중간에 우연히 나온 경우) 인용으로 취급하지 않는다."""
    answer, indices = _parse_cited_indices("[출처: 1] 이런 식으로 시작하는 답변입니다.")
    assert answer == "[출처: 1] 이런 식으로 시작하는 답변입니다."
    assert indices is None


def test_parse_cited_indices_trailing_whitespace_tolerated():
    answer, indices = _parse_cited_indices("답변입니다.\n[출처: 2]   \n  ")
    assert answer == "답변입니다."
    assert indices == {2}
