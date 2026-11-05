"""
config.is_confident() 유닛테스트 — 신뢰도 판정의 유일한 구현.

한 곳만 고치면 나머지가 조용히 낡던 문제(실시간/재분석/배치 세 경로가 각자
판정하다 배치 경로가 누락됐던 사례, config.py 문서 참고)를 막기 위해 이
함수 하나로 통일했다. 이 판정 자체가 틀리면 세 경로 전부가 동시에 틀리므로,
경계값 회귀를 유닛테스트로 지켜야 값이 크다.
"""
from stt.core.config import (
    CONF_AVG_LOGPROB_THRESHOLD, CONF_NO_SPEECH_THRESHOLD, is_confident,
)

EPS = 1e-6


class TestIsConfident:
    def test_both_none_passes(self):
        # 엔진이 신호를 안 주면(신호 부재) '신뢰 못 함'이 아니라 통과시킨다 —
        # 안 그러면 전부 저신뢰로 표시돼 플래그가 무의미해진다.
        assert is_confident(None, None) is True

    def test_avg_logprob_at_threshold_passes(self):
        # 문턱은 "미만"만 걸러낸다 — 정확히 문턱이면 통과.
        assert is_confident(CONF_AVG_LOGPROB_THRESHOLD, None) is True

    def test_avg_logprob_just_below_threshold_fails(self):
        assert is_confident(CONF_AVG_LOGPROB_THRESHOLD - EPS, None) is False

    def test_avg_logprob_above_threshold_passes(self):
        assert is_confident(CONF_AVG_LOGPROB_THRESHOLD + 0.05, None) is True

    def test_no_speech_prob_at_threshold_passes(self):
        # 문턱은 "초과"만 걸러낸다 — 정확히 문턱이면 통과.
        assert is_confident(None, CONF_NO_SPEECH_THRESHOLD) is True

    def test_no_speech_prob_just_above_threshold_fails(self):
        assert is_confident(None, CONF_NO_SPEECH_THRESHOLD + EPS) is False

    def test_no_speech_prob_below_threshold_passes(self):
        assert is_confident(None, CONF_NO_SPEECH_THRESHOLD - 0.1) is True

    def test_either_signal_failing_fails_overall(self):
        # avg_logprob은 통과해도 no_speech_prob이 걸리면 전체가 실패해야 한다
        good_logprob = CONF_AVG_LOGPROB_THRESHOLD + 0.1
        bad_no_speech = CONF_NO_SPEECH_THRESHOLD + 0.1
        assert is_confident(good_logprob, bad_no_speech) is False

    def test_both_signals_good_passes(self):
        good_logprob = CONF_AVG_LOGPROB_THRESHOLD + 0.1
        good_no_speech = CONF_NO_SPEECH_THRESHOLD - 0.1
        assert is_confident(good_logprob, good_no_speech) is True
