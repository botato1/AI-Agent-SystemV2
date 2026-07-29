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
    REALTIME_FLUSH_CHECK_INTERVAL_SEC,
    REALTIME_FLUSH_MIN_TAIL_SEC,
    REALTIME_FORCE_CUT_LOOKBACK_SEC,
    REALTIME_FORCE_CUT_MIN_SILENCE_MS,
    REALTIME_PARTIAL_INTERVAL_SEC,
    REALTIME_PARTIAL_MIN_SEC,
    FAST_BEAM_SIZE,
    PRECISE_BEAM_SIZE,
    REALTIME_FINAL_USES_FAST_MODEL,
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
    실시간 회의 오디오를 VAD 기준으로 청크 분할해 전사하는 세션.
    - 잠정 텍스트: 1초 주기로 Fast 모델(turbo)이 버퍼를 훑어 Local Agreement 방식으로 스트리밍
    - 확정 텍스트: 발화가 끊긴 지점에서 청크를 확정 전사.
      기본값은 Fast 모델(turbo) — 회의 중에는 응답성이 UX를 좌우하고, 정확도는 회의 종료 후
      정밀 재분석(large-v3)이 최종본을 다시 만들어 책임진다(REALTIME_FINAL_USES_FAST_MODEL).
      이 설정을 끄면 확정 전사도 Precise 모델(large-v3)이 담당한다.

    시간(초) 고정 분할 대신 '말이 끊기는 지점'을 기준으로 잘라야
    문장이 중간에 잘려 정확도가 떨어지는 걸 방지할 수 있음.
    """

    def __init__(
        self,
        session_id: str,
        fast_model: WhisperModel,
        precise_model: WhisperModel,
        speaker_identifier=None,
        recorder=None,
        fixed_speaker: str | None = None,
        base_offset_sec: float = 0.0,
        initial_prompt: str | None = None,
    ):
        self.session_id = session_id
        self.fast_model = fast_model
        self.precise_model = precise_model
        self.speaker_identifier = speaker_identifier  # LiveSpeakerIdentifier | None
        self.recorder = recorder  # MeetingRecord | None — 확정 청크를 디스크에 누적 저장
        # "각자 PC" 모드용 — 참가자가 자기 이름으로 직접 접속하면 이미 화자가
        # 확정돼 있으므로 임베딩 매칭(speaker_identifier) 없이 이 이름을 그대로 씀
        self.fixed_speaker = fixed_speaker
        # "각자 PC" 모드에서 이 참가자가 회의 시작 후 몇 초 뒤에 합류했는지.
        # 세그먼트 시각과 믹싱 오디오 위치를 "회의 전체 기준 절대 시각"으로 맞추는 데 필요
        # (참가자마다 자기 스트림 기준 0초부터 시작하므로, 이 오프셋을 더해야 서로 어긋나지 않음)
        self.base_offset_sec = base_offset_sec
        # 참석자 이름·팀 용어 인식 힌트 — 확정 전사(Precise)에만 적용한다.
        # 잠정 전사(partial)는 화면에 흘려보내는 용도이고 1초마다 도는 저지연 경로라,
        # 프롬프트 토큰만큼 디코딩 부담을 더 얹지 않는다(최종 텍스트는 어차피 확정본이 결정).
        self.initial_prompt = initial_prompt

        # 오디오 버퍼: 매 프레임 np.concatenate 하면 버퍼가 길어질수록 복사 비용이
        # O(n²)로 커지므로, 조각 리스트로 쌓아두고 필요할 때만 합침
        self._pending: list[np.ndarray] = []
        self._total_samples = 0
        self._elapsed_sec = 0.0
        self._last_flush_check = 0.0

        # Local Agreement 스트리밍 상태 (청크가 끝나기 전에도 실시간으로 텍스트를 흘려보내기 위함)
        self._last_partial_at = 0.0
        self._prev_partial_words: list[str] = []

    def push_audio(self, pcm16_bytes: bytes) -> None:
        """프론트에서 받은 PCM16LE(16kHz, mono) 오디오 바이트를 버퍼에 누적."""
        samples = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        self._pending.append(samples)
        self._total_samples += len(samples)

    def _materialize_buffer(self) -> np.ndarray:
        """조각 리스트를 하나의 배열로 합침. 합친 결과를 캐시해 반복 호출 비용을 줄임."""
        if not self._pending:
            return np.zeros(0, dtype=np.float32)
        if len(self._pending) > 1:
            self._pending = [np.concatenate(self._pending)]
        return self._pending[0]

    def _buffer_duration_sec(self) -> float:
        return self._total_samples / REALTIME_SAMPLE_RATE

    def should_flush(self) -> bool:
        """
        청크를 확정해도 되는 시점인지 판단.
        - 최소 길이(2초) 미만이면 아직 안 보냄
        - 최대 길이(28초)에 도달하면 침묵을 못 찾아도 강제로 자름 (지연 폭주 방지)
        - 그 사이엔 VAD로 '말이 끊긴 지점(500ms 이상 침묵)'을 찾으면 자름
        VAD는 버퍼 전체를 훑는 비싼 연산이라 매 프레임이 아니라 일정 주기로만 수행.
        """
        duration = self._buffer_duration_sec()
        if duration < REALTIME_MIN_CHUNK_SEC:
            return False
        if duration >= REALTIME_MAX_CHUNK_SEC:
            return True

        now = time.monotonic()
        if now - self._last_flush_check < REALTIME_FLUSH_CHECK_INTERVAL_SEC:
            return False
        self._last_flush_check = now

        buffer = self._materialize_buffer()
        speech_timestamps = get_speech_timestamps(
            buffer,
            VadOptions(min_silence_duration_ms=REALTIME_SILENCE_MS),
            sampling_rate=REALTIME_SAMPLE_RATE,
        )
        if not speech_timestamps:
            return False

        last_speech_end_sec = speech_timestamps[-1]["end"] / REALTIME_SAMPLE_RATE
        trailing_silence_ms = (duration - last_speech_end_sec) * 1000
        return trailing_silence_ms >= REALTIME_SILENCE_MS

    def _find_soft_cutoff(self, buffer: np.ndarray) -> int:
        """
        강제 컷(REALTIME_MAX_CHUNK_SEC 도달) 시 단어 중간이 잘리는 걸 피하기 위해,
        버퍼 끝 REALTIME_FORCE_CUT_LOOKBACK_SEC초 구간 안에서 짧은 틈(≥100ms)이라도
        있으면 그 지점을 자르는 위치로 반환. 못 찾으면 버퍼 길이(=끝에서 그냥 자름)를 반환.
        """
        lookback_samples = int(REALTIME_FORCE_CUT_LOOKBACK_SEC * REALTIME_SAMPLE_RATE)
        tail_start = max(0, len(buffer) - lookback_samples)
        tail = buffer[tail_start:]

        speech_spans = get_speech_timestamps(
            tail,
            VadOptions(min_silence_duration_ms=REALTIME_FORCE_CUT_MIN_SILENCE_MS),
            sampling_rate=REALTIME_SAMPLE_RATE,
        )
        # tail 안에 발화 구간이 2개 이상 있어야 그 사이에 실제 틈이 있다는 뜻.
        # 마지막 틈(=끝에서 가장 가까운 자연스러운 경계) 바로 앞에서 자름.
        if len(speech_spans) >= 2:
            return tail_start + speech_spans[-2]["end"]
        return len(buffer)

    def pop_chunk(self) -> tuple[np.ndarray, float]:
        """
        현재 버퍼를 청크로 확정하고 비움. (청크, 회의 시작 기준 오프셋 초) 반환.
        강제 컷 상황(버퍼가 최대 길이에 도달)이면 단어 중간이 안 잘리게 최근 구간에서
        짧은 틈을 찾아 그 지점까지만 확정하고, 나머지는 다음 청크로 이어서 넘김.
        """
        buffer = self._materialize_buffer()
        cutoff = len(buffer)
        if self._buffer_duration_sec() >= REALTIME_MAX_CHUNK_SEC:
            cutoff = self._find_soft_cutoff(buffer)

        chunk = buffer[:cutoff]
        leftover = buffer[cutoff:]

        offset_sec = self._elapsed_sec
        self._elapsed_sec += len(chunk) / REALTIME_SAMPLE_RATE

        if len(leftover) > 0:
            self._pending = [leftover]
            self._total_samples = len(leftover)
        else:
            self._pending = []
            self._total_samples = 0
        self._last_partial_at = 0.0
        self._prev_partial_words = []
        return chunk, offset_sec

    def _transcribe(
        self, model: WhisperModel, audio: np.ndarray, beam_size: int, initial_prompt: str | None = None
    ) -> list[dict]:
        segments, _info = model.transcribe(
            audio,
            language=WHISPER_LANGUAGE,
            beam_size=beam_size,
            vad_filter=True,
            initial_prompt=initial_prompt,
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
        # 공통 세그먼트 계약: {start, end, text, speaker, confident, user_edited}
        # — 정밀 재분석(refine_service) 결과와 같은 모양을 유지해야
        #   모순 감지 엔진이 refined 여부와 무관하게 동일한 필드를 참조할 수 있음
        for seg in segments:
            seg["start"] = round(seg["start"] + offset_sec, 2)
            seg["end"] = round(seg["end"] + offset_sec, 2)
            seg["confident"] = self._is_confident(seg)
            seg["user_edited"] = False

    async def process_chunk(self, audio: np.ndarray, offset_sec: float) -> dict:
        """
        확정 전사(Precise)와 화자 식별을 병렬로 실행.
        잠정 텍스트는 maybe_stream_partial()이 이미 흘려보냈으므로 여기선 확정본만 만든다.
        신뢰도 낮은 세그먼트(confident=False)는 호출 측(모순 감지 엔진)에서
        경고를 보류하고 다음 신호를 기다리는 판단 근거로 사용.
        """
        loop = asyncio.get_event_loop()
        started = time.monotonic()
        # 참가자 본인 스트림 기준 offset_sec에 회의 합류 시점을 더해 "회의 전체 기준
        # 절대 시각"으로 변환 (각자 PC 모드가 아니면 base_offset_sec=0이라 그대로임)
        offset_sec = offset_sec + self.base_offset_sec

        # 회의 중 자막은 사람이 기다리는 유일한 구간이라 응답성이 UX를 좌우한다.
        # 정확도는 회의 종료 후 정밀 재분석(large-v3)이 책임지므로, 여기서는 빠른 모델을 쓴다.
        # (실측: turbo 0.26초·건 vs large-v3 1.73초·건, 정확도 차 1.35%p — config 주석 참고)
        final_model = self.fast_model if REALTIME_FINAL_USES_FAST_MODEL else self.precise_model
        precise_task = loop.run_in_executor(
            None, self._transcribe, final_model, audio, PRECISE_BEAM_SIZE, self.initial_prompt
        )
        if self.fixed_speaker is not None:
            # 각자 PC 모드 — 참가자가 이미 자기 이름으로 접속했으므로 화자 식별 자체가 불필요
            precise_segments = await precise_task
            speaker_label = self.fixed_speaker
        elif self.speaker_identifier is not None:
            speaker_task = loop.run_in_executor(None, self.speaker_identifier.identify, audio)
            precise_segments, speaker_label = await asyncio.gather(precise_task, speaker_task)
        else:
            precise_segments = await precise_task
            speaker_label = None

        latency_sec = round(time.monotonic() - started, 2)
        self._apply_offset_and_confidence(precise_segments, offset_sec)
        if speaker_label is not None:
            for seg in precise_segments:
                seg["speaker"] = speaker_label

        if self.recorder is not None:
            # NAS 위 디스크 쓰기가 이벤트 루프(다른 회의의 실시간 스트리밍 포함)를 막지 않게 executor로
            await loop.run_in_executor(None, self.recorder.add_chunk, audio, precise_segments, offset_sec)

        logger.info(
            f"🎙️ [{self.session_id}] 청크 처리 완료 "
            f"(offset={offset_sec:.1f}s, latency={latency_sec}s, segs={len(precise_segments)}, speaker={speaker_label})"
        )

        return {
            "session_id": self.session_id,
            "type": "final",
            "chunk_offset_sec": round(offset_sec, 2),
            "speaker": speaker_label,
            "latency_sec": latency_sec,
            "final": {"segments": precise_segments},
        }

    def rename_speaker(self, old_name: str, new_name: str) -> bool:
        """
        진행 중인 회의의 화자 이름 교체 — rename API에서 호출됨.
        살아있는 식별기(이후 청크의 라벨)와 회의록(과거 세그먼트 + C-4용 프로필
        스냅샷)을 함께 갱신해서 한 회의 안에서 이름이 섞이지 않게 함.
        (recorder 쪽은 블로킹 I/O — executor에서 호출할 것)
        """
        renamed = False
        if self.fixed_speaker == old_name:
            self.fixed_speaker = new_name
            renamed = True
        if self.speaker_identifier is not None:
            renamed = self.speaker_identifier.rename_speaker(old_name, new_name) or renamed
        if self.recorder is not None:
            renamed = self.recorder.rename_speaker(old_name, new_name) or renamed
        return renamed

    async def flush_remaining(self) -> dict | None:
        """
        회의 종료(또는 연결 종료 직전) 시 아직 청크로 확정 안 된 잔여 버퍼를 마지막
        청크로 처리. 이게 없으면 회의 마지막 발언이 조용히 유실된다.
        노이즈 수준(0.5초 미만)이면 버림.
        """
        if self._buffer_duration_sec() < REALTIME_FLUSH_MIN_TAIL_SEC:
            return None
        chunk, offset_sec = self.pop_chunk()
        return await self.process_chunk(chunk, offset_sec)

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

        buffer = self._materialize_buffer()
        loop = asyncio.get_event_loop()
        segments = await loop.run_in_executor(
            None, self._transcribe, self.fast_model, buffer, FAST_BEAM_SIZE
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
