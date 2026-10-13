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
