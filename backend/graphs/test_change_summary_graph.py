# backend/graphs/test_change_summary_graph.py

from backend.graphs.nodes.change_summary_generate import build_summary_prompt


def test_build_summary_prompt_includes_original_and_accepted():
    prompt = build_summary_prompt("예산 500만원", "예산 800만원", None)
    assert "예산 500만원" in prompt
    assert "예산 800만원" in prompt
    assert "(추가 맥락 없음)" in prompt


def test_build_summary_prompt_includes_base_summary_when_present():
    prompt = build_summary_prompt("A", "B", "이전 회의에서 예산 논의가 있었음")
    assert "이전 회의에서 예산 논의가 있었음" in prompt
    assert "(추가 맥락 없음)" not in prompt


def test_build_summary_prompt_empty_base_summary_string_treated_as_missing():
    prompt = build_summary_prompt("A", "B", "")
    assert "(추가 맥락 없음)" in prompt
