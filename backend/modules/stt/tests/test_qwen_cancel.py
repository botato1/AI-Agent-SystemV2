"""Qwen 엔진의 협력적 취소 — 버려진 전체 청크 전사가 GPU를 계속 쓰지 않게 하는 경로."""
import threading

import numpy as np
import pytest
import torch

try:
    from stt.services import qwen_engine
except Exception as exc:  # transformers 버전이 모델 클래스를 못 가져오는 환경(맥 등)
    pytest.skip(f"qwen_engine import 불가: {exc}", allow_module_level=True)


def test_criteria_follows_event():
    event = threading.Event()
    crit = qwen_engine._CancelCriteria(event)
    ids = torch.zeros((1, 4), dtype=torch.long)
    assert not crit(ids, None).any()
    event.set()
    assert crit(ids, None).all()


def _engine_without_model():
    engine = object.__new__(qwen_engine.Qwen3ASREngine)
    engine.default_context = None
    return engine


def _speech(seconds):
    t = np.arange(int(seconds * 16000)) / 16000
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_transcribe_stops_before_next_window(monkeypatch):
    engine = _engine_without_model()
    event = threading.Event()
    calls = []

    def fake_generate(window, language, beam_size, context, cancel_event=None):
        calls.append(len(window))
        event.set()  # 첫 창을 돌리는 도중 취소가 들어온 상황
        return "텍스트", -0.1

    monkeypatch.setattr(engine, "_generate_window", fake_generate)
    monkeypatch.setattr(qwen_engine, "trim_silence", lambda a: (a, True, 0.0))
    segments, _ = engine.transcribe(_speech(70), vad_filter=True, cancel_event=event)
    assert segments == []
    assert len(calls) == 1


def test_transcribe_without_event_unchanged(monkeypatch):
    engine = _engine_without_model()
    monkeypatch.setattr(engine, "_generate_window", lambda *a, **k: ("가나다", -0.1))
    monkeypatch.setattr(qwen_engine, "trim_silence", lambda a: (a, True, 0.0))
    segments, _ = engine.transcribe(_speech(5), vad_filter=True)
    assert [s.text for s in segments] == ["가나다"]


def test_decode_kwargs_static_only_when_fast_decode():
    engine = _engine_without_model()
    engine.fast_decode = False
    assert engine._decode_kwargs() == {}
    engine.fast_decode = True
    assert engine._decode_kwargs() == {"cache_implementation": "static"}


def test_fast_decode_skips_generate_when_cancelled_while_waiting(monkeypatch):
    """락을 기다리는 사이 취소되면 generate를 부르지 않는다."""
    engine = _engine_without_model()
    engine.fast_decode = True
    engine._decode_lock = threading.Lock()

    class _Inputs(dict):
        def to(self, *a, **k):
            return self

    class _Proc:
        def apply_chat_template(self, *a, **k):
            return _Inputs(input_ids=torch.zeros((1, 3), dtype=torch.long))

    class _Model:
        device, dtype = "cpu", torch.float32
        called = False

        def generate(self, **k):
            _Model.called = True
            raise AssertionError("취소됐으면 부르면 안 된다")

    engine.processor = _Proc()
    engine.model = _Model()
    monkeypatch.setattr(engine, "_build_conversation", lambda *a, **k: [])
    event = threading.Event()
    event.set()
    text, _lp = engine._generate_window(_speech(1), "ko", 1, None, event)
    assert text == "" and not _Model.called
