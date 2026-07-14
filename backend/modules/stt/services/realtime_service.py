import asyncio
import time
import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions, get_speech_timestamps

from ..core.config import (
    logger,
    WHISPER_LANGUAGE,
    REALTIME_SAMPLE_RATE,
    REALTIME_MIN_CHUNK_SEC,
    REALTIME_MAX_CHUNK_SEC,
    REALTIME_SILENCE_MS,
    REALTIME_PARTIAL_INTERVAL_SEC,
    REALTIME_PARTIAL_MIN_SEC,
    REALTIME_INITIAL_PROMPT,
    FAST_BEAM_SIZE,
    PRECISE_BEAM_SIZE,
    CONF_AVG_LOGPROB_THRESHOLD,
    CONF_NO_SPEECH_THRESHOLD,
)


def _longest_common_prefix(a: list[str], b: list[str]) -> list[str]:
    """두 단어 리스트에서 앞에서부터 일치하는 부분만 뽑음 (Local Agreement 핵심 로직)."""
    prefix = []
    for x, y in zip(a, b):
        if x != y:
            break
        prefix.append(x)
    return prefix


class RealtimeSTTSession:
    """
    실시간 회의 오디오를 VAD 기준으로 청크 분할해
    Fast Pass(즉시, 저정밀) → Precise Pass(확정, 고정밀) 순서로 전사하는 세션.

    시간(초) 고정 분할 대신 '말이 끊기는 지점'을 기준으로 잘라야
    문장이 중간에 잘려 정확도가 떨어지는 걸 방지할 수 있음.
    """

    def __init__(
        self,
        session_id: str,
        fast_model: WhisperModel,
        precise_model: WhisperModel,
        speaker_identifier=None,
    ):
        self.session_id = session_id
        self.fast_model = fast_model
        self.precise_model = precise_model
        self.speaker_identifier = speaker_identifier  # LiveSpeakerIdentifier | None
        self._buffer = np.zeros(0, dtype=np.float32)
        self._elapsed_sec = 0.0

        # Local Agreement 스트리밍 상태 (청크가 끝나기 전에도 실시간으로 텍스트를 흘려보내기 위함)
        self._last_partial_at = 0.0
        self._prev_partial_words: list[str] = []

    def push_audio(self, pcm16_bytes: bytes) -> None:
        """프론트에서 받은 PCM16LE(16kHz, mono) 오디오 바이트를 버퍼에 누적."""
        samples = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        self._buffer = np.concatenate([self._buffer, samples])

    def _buffer_duration_sec(self) -> float:
        return len(self._buffer) / REALTIME_SAMPLE_RATE

    def should_flush(self) -> bool:
        """
        청크를 확정해도 되는 시점인지 판단.
        - 최소 길이(2초) 미만이면 아직 안 보냄
        - 최대 길이(28초)에 도달하면 침묵을 못 찾아도 강제로 자름 (지연 폭주 방지)
        - 그 사이엔 VAD로 '말이 끊긴 지점(500ms 이상 침묵)'을 찾으면 자름
        """
        duration = self._buffer_duration_sec()
        if duration < REALTIME_MIN_CHUNK_SEC:
            return False
        if duration >= REALTIME_MAX_CHUNK_SEC:
            return True

        speech_timestamps = get_speech_timestamps(
            self._buffer,
            VadOptions(min_silence_duration_ms=REALTIME_SILENCE_MS),
            sampling_rate=REALTIME_SAMPLE_RATE,
        )
        if not speech_timestamps:
            return False

        last_speech_end_sec = speech_timestamps[-1]["end"] / REALTIME_SAMPLE_RATE
        trailing_silence_ms = (duration - last_speech_end_sec) * 1000
        return trailing_silence_ms >= REALTIME_SILENCE_MS

    def pop_chunk(self) -> tuple[np.ndarray, float]:
        """현재 버퍼를 청크로 확정하고 비움. (청크, 회의 시작 기준 오프셋 초) 반환."""
        chunk = self._buffer
        offset_sec = self._elapsed_sec
        self._elapsed_sec += self._buffer_duration_sec()
        self._buffer = np.zeros(0, dtype=np.float32)
        self._last_partial_at = 0.0
        self._prev_partial_words = []
        return chunk, offset_sec

    def _transcribe(self, model: WhisperModel, audio: np.ndarray, beam_size: int) -> list[dict]:
        segments, _info = model.transcribe(
            audio,
            language=WHISPER_LANGUAGE,
            beam_size=beam_size,
            vad_filter=True,
            initial_prompt=REALTIME_INITIAL_PROMPT,
            condition_on_previous_text=False,
        )
        return [
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
                "avg_logprob": seg.avg_logprob,
                "no_speech_prob": seg.no_speech_prob,
            }
            for seg in segments
        ]

    def _is_confident(self, seg: dict) -> bool:
        return (
            seg["avg_logprob"] >= CONF_AVG_LOGPROB_THRESHOLD
            and seg["no_speech_prob"] <= CONF_NO_SPEECH_THRESHOLD
        )

    def _apply_offset_and_confidence(self, segments: list[dict], offset_sec: float) -> None:
        for seg in segments:
            seg["start"] = round(seg["start"] + offset_sec, 2)
            seg["end"] = round(seg["end"] + offset_sec, 2)
            seg["confident"] = self._is_confident(seg)

    async def process_chunk(self, audio: np.ndarray, offset_sec: float) -> dict:
        """
        Fast Pass와 Precise Pass를 동시에 GPU에 던져서 병렬로 처리 (순차 대기 대비 지연 감소).
        신뢰도 낮은 세그먼트(confident=False)는 호출 측(모순 감지 엔진)에서
        경고를 보류하고 다음 신호를 기다리는 판단 근거로 사용.
        """
        loop = asyncio.get_event_loop()

        fast_start = time.monotonic()
        fast_task = loop.run_in_executor(None, self._transcribe, self.fast_model, audio, FAST_BEAM_SIZE)
        precise_task = loop.run_in_executor(None, self._transcribe, self.precise_model, audio, PRECISE_BEAM_SIZE)

        fast_segments, precise_segments = await asyncio.gather(fast_task, precise_task)
        fast_latency_sec = round(time.monotonic() - fast_start, 2)

        self._apply_offset_and_confidence(fast_segments, offset_sec)
        self._apply_offset_and_confidence(precise_segments, offset_sec)

        speaker_label = None
        if self.speaker_identifier is not None:
            speaker_label = await loop.run_in_executor(None, self.speaker_identifier.identify, audio)
            for seg in precise_segments:
                seg["speaker"] = speaker_label

        logger.info(
            f"🎙️ [{self.session_id}] 청크 처리 완료 "
            f"(offset={offset_sec:.1f}s, fast={fast_latency_sec}s, "
            f"fast_segs={len(fast_segments)}, precise_segs={len(precise_segments)})"
        )

        return {
            "session_id": self.session_id,
            "type": "final",
            "chunk_offset_sec": round(offset_sec, 2),
            "speaker": speaker_label,
            "draft": {"latency_sec": fast_latency_sec, "segments": fast_segments},
            "final": {"segments": precise_segments},
        }

    async def maybe_stream_partial(self) -> dict | None:
        """
        Local Agreement 스트리밍: 청크가 끝나길(VAD 침묵) 기다리지 않고,
        1초 주기로 지금까지 쌓인 버퍼 전체를 Fast 모델로 다시 훑어서
        '이전 결과와 일치하는 앞부분'만 확정 텍스트로 흘려보낸다.
        발화자가 안 쉬고 계속 말해도 화면에 실시간으로 텍스트가 갱신되는 효과.
        확정 여부는 결국 process_chunk()의 Precise Pass가 최종 보정한다.
        """
        now = time.monotonic()
        if now - self._last_partial_at < REALTIME_PARTIAL_INTERVAL_SEC:
            return None
        if self._buffer_duration_sec() < REALTIME_PARTIAL_MIN_SEC:
            return None
        self._last_partial_at = now

        loop = asyncio.get_event_loop()
        segments = await loop.run_in_executor(
            None, self._transcribe, self.fast_model, self._buffer, FAST_BEAM_SIZE
        )
        text = " ".join(seg["text"] for seg in segments).strip()
        words = text.split()

        confirmed_words = _longest_common_prefix(self._prev_partial_words, words)
        tentative_words = words[len(confirmed_words):]
        self._prev_partial_words = words

        return {
            "session_id": self.session_id,
            "type": "partial",
            "confirmed_text": " ".join(confirmed_words),
            "tentative_text": " ".join(tentative_words),
        }
