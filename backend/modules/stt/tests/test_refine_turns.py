"""
refine_service.py의 결정론적 경계 로직(_merge_adjacent_turns, _free_pieces,
_resolve_overlapping_turns) 유닛테스트.

왜 필요한가: 이 로직들은 GPU/모델 없이도 순수 함수로 동작하는데, 지금까지는
실제 회의로 cpCER을 재는 방식으로만 검증돼 왔다(finetune/stt/evaluate_against_script.py).
그 방식은 화자 판정처럼 "정답이 분포로만 존재하는" 로직엔 맞지만, 여기처럼
입력→출력이 결정론적인 경계 조건(턴 병합 간격, 겹침 우선순위)은 훨씬 싸고
빠르게 유닛테스트로 지킬 수 있다.
"""
from stt.services.refine_service import (
    MAX_TURN_GAP_SEC, MIN_TRIMMED_TURN_SEC,
    _free_pieces, _merge_adjacent_turns, _resolve_overlapping_turns,
)


def _turn(speaker, start, end):
    return {"speaker": speaker, "start": start, "end": end}


class TestMergeAdjacentTurns:
    def test_merges_same_speaker_within_gap(self):
        tracks = [_turn("A", 0.0, 2.0), _turn("A", 2.0 + MAX_TURN_GAP_SEC, 5.0)]
        merged = _merge_adjacent_turns(tracks)
        assert merged == [_turn("A", 0.0, 5.0)]

    def test_does_not_merge_beyond_gap(self):
        tracks = [_turn("A", 0.0, 2.0), _turn("A", 2.0 + MAX_TURN_GAP_SEC + 0.01, 5.0)]
        merged = _merge_adjacent_turns(tracks)
        assert len(merged) == 2

    def test_does_not_merge_different_speakers_even_if_adjacent(self):
        tracks = [_turn("A", 0.0, 2.0), _turn("B", 2.0, 3.0)]
        merged = _merge_adjacent_turns(tracks)
        assert len(merged) == 2

    def test_sorts_by_start_before_merging(self):
        # 화자분리 결과가 시간 순으로 안 들어와도 병합이 맞아야 한다
        tracks = [_turn("A", 3.0, 5.0), _turn("A", 0.0, 2.0)]
        merged = _merge_adjacent_turns(tracks)
        assert merged == [_turn("A", 0.0, 5.0)]

    def test_empty_input(self):
        assert _merge_adjacent_turns([]) == []


class TestFreePieces:
    def test_no_occupied_returns_whole_range(self):
        assert _free_pieces(0.0, 10.0, []) == [(0.0, 10.0)]

    def test_occupied_in_middle_splits_into_two(self):
        assert _free_pieces(0.0, 10.0, [(4.0, 6.0)]) == [(0.0, 4.0), (6.0, 10.0)]

    def test_occupied_covers_whole_range(self):
        assert _free_pieces(0.0, 10.0, [(0.0, 10.0)]) == []

    def test_occupied_outside_range_ignored(self):
        assert _free_pieces(5.0, 10.0, [(0.0, 3.0), (12.0, 15.0)]) == [(5.0, 10.0)]

    def test_multiple_occupied_pieces(self):
        occupied = [(1.0, 2.0), (4.0, 5.0), (7.0, 8.0)]
        assert _free_pieces(0.0, 10.0, occupied) == [
            (0.0, 1.0), (2.0, 4.0), (5.0, 7.0), (8.0, 10.0),
        ]


class TestResolveOverlappingTurns:
    def test_no_overlap_keeps_all(self):
        turns = [_turn("A", 0.0, 2.0), _turn("B", 3.0, 5.0)]
        result = _resolve_overlapping_turns(turns)
        assert len(result) == 2

    def test_longer_turn_wins_over_shorter_fully_contained(self):
        # 실제 사례(refine_service.py 문서): 문지수의 긴 턴 안에 김나연의 짧은
        # 맞장구가 완전히 들어있으면, 짧은 쪽은 버려진다(그 소리는 이미 긴 턴
        # 안에서 전사되므로 내용을 잃는 게 아니다).
        turns = [_turn("문지수", 27.3, 34.9), _turn("김나연", 27.3, 27.9)]
        result = _resolve_overlapping_turns(turns)
        assert len(result) == 1
        assert result[0]["speaker"] == "문지수"

    def test_partial_overlap_trims_shorter_turn(self):
        turns = [_turn("A", 0.0, 10.0), _turn("B", 8.0, 12.0)]
        result = _resolve_overlapping_turns(turns)
        assert len(result) == 2
        b = next(t for t in result if t["speaker"] == "B")
        assert b["start"] == 10.0
        assert b["end"] == 12.0

    def test_trimmed_remainder_below_min_is_dropped(self):
        # 겹침을 걷어내고 남은 조각이 MIN_TRIMMED_TURN_SEC보다 짧으면 버린다 —
        # 잘려나간 끄트머리는 전사해봐야 헛것이 나오는 부스러기이기 때문.
        # B는 대부분 A 안에 있고, A의 끝(10.0)보다 아주 살짝만(MIN 미만) 삐져나온다.
        tail = MIN_TRIMMED_TURN_SEC - 0.01
        turns = [_turn("A", 0.0, 10.0), _turn("B", 9.0, 10.0 + tail)]
        result = _resolve_overlapping_turns(turns)
        assert len(result) == 1
        assert result[0]["speaker"] == "A"

    def test_result_sorted_by_start(self):
        turns = [_turn("B", 5.0, 7.0), _turn("A", 0.0, 2.0)]
        result = _resolve_overlapping_turns(turns)
        assert [t["speaker"] for t in result] == ["A", "B"]
