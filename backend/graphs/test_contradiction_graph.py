# backend/graphs/test_contradiction_graph.py

# run_contradiction_detection()의 입력 검증만 다루는 가벼운 단위 테스트.
# 그래프 실행(DB/ChromaDB/Ollama 호출)까지는 다루지 않는다 — 이 저장소에
# 아직 테스트 픽스처/모킹 컨벤션이 없어서, 검증 로직만 우선 커버한다.

import pytest

from backend.graphs.contradiction_graph import run_contradiction_detection

_COMMON_KWARGS = dict(
    workspace_id="11111111-1111-1111-1111-111111111111",
    category_id="22222222-2222-2222-2222-222222222222",
    statement_text="DB는 MongoDB로 바꾸자",
)


def test_unknown_source_type_raises():
    with pytest.raises(ValueError):
        run_contradiction_detection(
            **_COMMON_KWARGS,
            source_type="unknown_type",
            meeting_segment_id="33333333-3333-3333-3333-333333333333",
        )


def test_meeting_segment_without_id_raises():
    with pytest.raises(ValueError):
        run_contradiction_detection(
            **_COMMON_KWARGS,
            source_type="meeting_segment",
        )


def test_meeting_segment_with_both_ids_raises():
    with pytest.raises(ValueError):
        run_contradiction_detection(
            **_COMMON_KWARGS,
            source_type="meeting_segment",
            meeting_segment_id="33333333-3333-3333-3333-333333333333",
            room_message_id="44444444-4444-4444-4444-444444444444",
        )


def test_room_message_without_id_raises():
    with pytest.raises(ValueError):
        run_contradiction_detection(
            **_COMMON_KWARGS,
            source_type="room_message",
        )
