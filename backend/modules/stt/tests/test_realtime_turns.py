"""
realtime_service.py의 _absorb_short_turns 유닛테스트.

이 로직은 실측(2026-08-20, 팀 제보)으로 잡은 실제 버그 두 개를 방지하는
안전장치다 — "짧은 턴은 실수로 갈라진 조각"이라는 가정과 "첫 턴이 짧으면
뒤로 흡수해야 한다"는 방향성 둘 다 회귀하면 안 된다.
"""
from stt.services.realtime_service import _absorb_short_turns

MIN = 100  # 임의의 최소 샘플 수(초 단위 환산 없이 순수 로직만 검증)


class TestAbsorbShortTurns:
    def test_no_short_turns_unchanged(self):
        turns = [(0, 200, "A"), (200, 400, "B")]
        assert _absorb_short_turns(turns, MIN) == turns

    def test_short_middle_turn_absorbed_into_previous(self):
        # 기본은 앞 턴에 흡수
        turns = [(0, 200, "A"), (200, 250, "B"), (250, 450, "C")]
        result = _absorb_short_turns(turns, MIN)
        assert result == [(0, 250, "A"), (250, 450, "C")]

    def test_short_first_turn_absorbed_into_next(self):
        # 실측 버그: "개발."(짧음, 미상) + "진행 상황..."(이승주)가 따로 턴이 되던
        # 문제 — 첫 턴이 짧으면 흡수할 앞이 없으므로 다음 턴에 흡수돼야 한다.
        turns = [(0, 30, None), (30, 230, "이승주")]
        result = _absorb_short_turns(turns, MIN)
        assert result == [(0, 230, "이승주")]

    def test_single_short_turn_with_nothing_to_absorb_into_stays(self):
        turns = [(0, 30, "A")]
        result = _absorb_short_turns(turns, MIN)
        assert result == [(0, 30, "A")]

    def test_first_two_consecutive_short_turns_merge_forward(self):
        # 맨 앞 두 턴이 짧으면(합쳐도 아직 짧을 수 있음) 첫 턴은 두 번째 턴에
        # 흡수되고, 그 결과 턴은 세 번째(짧지 않은) 턴과는 별도로 남는다 —
        # 흡수는 한 단계만 미리 본다(캐스케이드하지 않는다).
        turns = [(0, 20, None), (20, 40, None), (40, 240, "A")]
        result = _absorb_short_turns(turns, MIN)
        assert result == [(0, 40, None), (40, 240, "A")]

    def test_absorbed_label_is_the_surviving_neighbor(self):
        # 앞 턴에 흡수될 때 라벨은 앞 턴(생존 턴) 것을 유지해야 한다
        turns = [(0, 200, "A"), (200, 250, "B")]
        result = _absorb_short_turns(turns, MIN)
        assert result == [(0, 250, "A")]
