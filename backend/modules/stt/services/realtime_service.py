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
    REALTIME_PARTIAL_SPEAKER_TAIL_SEC,
    REALTIME_SPEAKER_SPLIT_ENABLED,
    REALTIME_SPEAKER_SPLIT_SILENCE_MS,
    REALTIME_SPEAKER_SCAN_ENABLED,
    REALTIME_SPEAKER_SCAN_MIN_SEC,
    REALTIME_SPEAKER_SCAN_HOP_SEC,
    SPEAKER_WINDOW_SEC,
    SPEAKER_SMOOTH_WIDTH,
    FAST_BEAM_SIZE,
    PRECISE_BEAM_SIZE,
    REALTIME_FINAL_USES_FAST_MODEL,
    is_confident,
)
from .audio_quality import AudioQualityMonitor
from .speaker_timeline import find_speaker_runs


# 임베딩이 불안정해지는 하한 — speaker_id_service._MIN_EMBED_SEC(1.0초)와 맞춘 값.
# 이보다 짧으면 목소리 특성보다 발음 내용에 휘둘려 엉뚱한 화자로 튄다.
_MIN_PARTIAL_SPEAKER_SAMPLES = REALTIME_SAMPLE_RATE

# 화자 전환으로 청크를 나눌 때 각 턴의 최소 길이. 이보다 짧으면 앞 턴에 흡수한다.
# 임베딩 하한(1초)보다 넉넉히 잡는다 — 딱 1초짜리 오디오로는 판정이 흔들린다.
_MIN_SPLIT_TURN_SAMPLES = int(1.5 * REALTIME_SAMPLE_RATE)

# "판정했는데 등록된 누구와도 안 닮음"을 나타내는 내부 표식.
#
# None과 반드시 구분해야 한다. None은 "구간이 짧아 판정 자체가 불가"라는 뜻이고
# 이웃 화자를 승계하는데, 미상을 None으로 뭉뚱그리면 그 구간이 이웃 라벨을 물려받아
# **화자 경계가 지워진다** — 실측에서 분할이 6회→3회로 줄고 세 사람이 28초짜리 한
# 덩어리로 묶인 원인이 이것이었다. 미상은 승계 대상이 아니라 그 자체로 경계다.
_UNKNOWN_SPEAKER = "\x00unknown"


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
    - 잠정 텍스트: 1초 주기로 Fast 모델이 버퍼를 훑어 Local Agreement 방식으로 스트리밍.
      화자도 함께 판정해 붙인다(_partial_speaker).
    - 확정 텍스트: 발화가 끊긴 지점에서 Precise 모델로 확정 전사.
      REALTIME_FINAL_USES_FAST_MODEL=1이면 확정도 Fast 모델이 담당한다(속도 우선).

    Fast/Precise가 어느 모델인지는 엔진 설정에 따라 다르다 — config.py의
    WHISPER_MODEL_FAST / WHISPER_MODEL_PRECISE 참고. Fast를 따로 두는 이유는
    정확도가 아니라 **지연**이다: 잠정 전사는 1초마다 버퍼 전체를 다시 훑기 때문에
    여기에 확정용 모델을 쓰면 전사 큐가 포화되고 오디오 프레임이 버려진다(실측 확인).

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
        # 회의 중 오디오 상태 감시 — 인식이 무너질 조건이면 초반에 알린다
        self.audio_quality = AudioQualityMonitor()

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

    def _apply_offset_and_confidence(self, segments: list[dict], offset_sec: float) -> None:
        # 공통 세그먼트 계약: {start, end, text, speaker, confident, user_edited}
        # — 정밀 재분석(refine_service) 결과와 같은 모양을 유지해야
        #   모순 감지 엔진이 refined 여부와 무관하게 동일한 필드를 참조할 수 있음
        for seg in segments:
            seg["start"] = round(seg["start"] + offset_sec, 2)
            seg["end"] = round(seg["end"] + offset_sec, 2)
            seg["confident"] = is_confident(seg.get("avg_logprob"), seg.get("no_speech_prob"))
            seg["user_edited"] = False

    def _speaker_turns(self, audio: np.ndarray) -> list[tuple[int, int, str | None]]:
        """
        청크를 화자 턴 단위로 나눈다. [(시작 샘플, 끝 샘플, 화자), ...]

        왜 필요한가: 청크는 VAD가 침묵을 찾을 때까지 최대 28초까지 늘어난다. 두 사람이
        쉼 없이 주고받으면 한 청크에 여러 화자가 들어가는데, 청크당 라벨 하나만 붙이면
        질문과 답변이 한 사람 발언으로 묶인다.

        동작:
          1. VAD로 발화 구간을 뽑고
          2. 구간마다 목소리로 화자를 판정하고(읽기 전용 — 프로필은 아래 3에서만 갱신)
          3. 연속된 같은 화자를 하나의 턴으로 병합

        **화자 전환이 없으면 턴 하나만 돌려준다** — 이 경우 호출부는 기존과 똑같이
        전사를 한 번만 하므로 추가 비용이 없다. 대부분의 청크가 여기 해당한다.

        턴 경계는 다음 턴의 첫 발화 시작점으로 잡는다. 구간 사이 침묵도 어느 한 턴에
        반드시 포함시켜야 오디오가 새지 않는다(전사 입력에서 빠지면 말이 잘린다).
        """
        # 청크를 끊는 기준(REALTIME_SILENCE_MS)보다 짧은 침묵을 본다. 같은 값을 쓰면
        # 간격이 그보다 길 때 청크가 이미 끊겨 있어 분할할 대상이 없다 — 기능이 죽는다.
        spans = get_speech_timestamps(
            audio, VadOptions(min_silence_duration_ms=REALTIME_SPEAKER_SPLIT_SILENCE_MS),
            sampling_rate=REALTIME_SAMPLE_RATE,
        )
        if len(spans) < 2:
            # 침묵이 없다 = 쉼 없이 이어 말했다. 여기서 포기하면 두 사람 발화가
            # 한 덩어리로 묶여 자막에 틀린 이름이 뜬다(팀 제보 사례).
            # 목소리 변화로 한 번 더 찾아본다.
            return self._scan_speaker_changes(audio)

        # 각 발화 구간의 화자 판정. 너무 짧은 구간은 임베딩이 불안정해 판정을 포기하고
        # (None) 아래에서 이웃 구간의 화자를 승계한다 — "네", "음" 같은 짧은 맞장구가
        # 엉뚱한 화자로 튀어 턴을 잘게 쪼개는 걸 막는다.
        labels: list[str | None] = []
        for span in spans:
            piece = audio[span["start"]:span["end"]]
            if len(piece) < _MIN_PARTIAL_SPEAKER_SAMPLES:
                labels.append(None)          # 짧아서 판정 불가 → 아래에서 이웃 승계
            else:
                # 판정은 됐지만 누구와도 안 닮은 경우(하한 미달)는 이웃을 승계하면 안 된다.
                # 그 자체로 화자 경계이므로 별도 표식을 둔다.
                labels.append(self.speaker_identifier.identify(piece, update_profile=False)
                              or _UNKNOWN_SPEAKER)

        # 판정 못 한 구간을 앞쪽 이웃으로, 앞이 없으면 뒤쪽 이웃으로 채운다
        for i, label in enumerate(labels):
            if label is not None:
                continue
            prev = next((labels[j] for j in range(i - 1, -1, -1) if labels[j] is not None), None)
            nxt = next((labels[j] for j in range(i + 1, len(labels)) if labels[j] is not None), None)
            labels[i] = prev if prev is not None else nxt

        # 연속 동일 화자 병합 → 턴 경계
        turns: list[tuple[int, int, str | None]] = []
        turn_start = 0
        for i in range(1, len(spans)):
            if labels[i] == labels[i - 1]:
                continue
            turns.append((turn_start, spans[i]["start"], labels[i - 1]))
            turn_start = spans[i]["start"]
        turns.append((turn_start, len(audio), labels[-1]))
        # 내부 표식은 밖으로 내보내지 않는다 — 호출부는 None(미상)으로 받는다
        turns = [(a, b, None if c == _UNKNOWN_SPEAKER else c) for a, b, c in turns]

        # 너무 짧은 턴은 앞 턴에 흡수한다. 턴이 짧을수록 화자 판정에 쓸 오디오가 줄어
        # 라벨이 흔들리고, 전사도 문맥이 끊겨 나빠진다. 맞장구("네", "아 그래요") 하나
        # 때문에 긴 발화를 쪼개는 건 얻는 것보다 잃는 게 크다.
        merged: list[tuple[int, int, str | None]] = []
        for start, end, label in turns:
            too_short = (end - start) < _MIN_SPLIT_TURN_SAMPLES
            if too_short and merged:
                prev_start, _, prev_label = merged[-1]
                merged[-1] = (prev_start, end, prev_label)
            elif too_short and not merged:
                merged.append((start, end, label))   # 첫 턴은 흡수할 앞이 없다
            else:
                merged.append((start, end, label))
        return merged

    def _scan_speaker_changes(self, audio: np.ndarray) -> list[tuple[int, int, str | None]]:
        """
        침묵으로 못 나눈 오디오를 **목소리 변화**로 나눈다.

        침묵 기준은 "쉼 없이 주고받는" 대화를 못 나눈다 — 나눌 침묵 자체가 없다.
        실측(팀 제보): "네, 제가 이번 주 안으로 반영해 볼게요. 감사합니다. 오늘은
        여기까지 할게요."가 한 사람으로 묶였다(앞은 김나연, 뒤는 문지수).

        비용은 창 수에 비례하고 그게 곧 확정 자막의 지연이므로:
          - 짧은 청크는 건너뛴다(짧으면 화자가 바뀔 여지도 적다)
          - 재분석(0.5초)보다 성기게 훑는다
          - 등록 프로필이 없으면 순위 판정 자체가 성립하지 않아 하지 않는다
        """
        if (
            not REALTIME_SPEAKER_SCAN_ENABLED
            or not self.speaker_identifier._closed_set
            or len(audio) < REALTIME_SPEAKER_SCAN_MIN_SEC * REALTIME_SAMPLE_RATE
        ):
            return [(0, len(audio), None)]

        runs = find_speaker_runs(
            audio, self.speaker_identifier, REALTIME_SAMPLE_RATE,
            window_sec=SPEAKER_WINDOW_SEC,
            hop_sec=REALTIME_SPEAKER_SCAN_HOP_SEC,
            smooth_width=SPEAKER_SMOOTH_WIDTH,
        )
        if len(runs) > 1:
            names = " → ".join(name or "미상" for _s, _e, name in runs)
            logger.info(f"🔍 목소리 변화로 화자 전환 감지(침묵 없음): {names}")
        return runs

    async def _transcribe_with_speakers(self, audio, precise_task, final_model):
        """
        화자 전환을 반영해 전사한다. (세그먼트 목록, 대표 화자)를 반환.

        화자 전환이 없으면(대부분) 이미 시작해둔 precise_task를 그대로 쓰고 화자만
        붙인다 — 전사와 화자 판정이 병렬로 도는 기존 경로 그대로다.
        전환이 있을 때만 그 전사를 버리고 턴별로 다시 전사한다. 버려지는 비용이 있지만,
        전환은 소수이고 미리 시작해두는 편이 대부분의 청크에서 이득이다.

        대표 화자는 청크에서 가장 오래 말한 사람 — 회의록 오디오 저장(recorder)이
        청크당 화자 하나를 받기 때문에 필요하다.
        """
        loop = asyncio.get_event_loop()

        if not REALTIME_SPEAKER_SPLIT_ENABLED:
            speaker_task = loop.run_in_executor(None, self.speaker_identifier.identify, audio)
            segments, speaker = await asyncio.gather(precise_task, speaker_task)
            return segments, speaker

        turns = await loop.run_in_executor(None, self._speaker_turns, audio)

        if len(turns) < 2:
            # 화자 전환 없음 — 청크 전체로 한 번 판정(프로필 갱신 포함)하고 끝.
            speaker_task = loop.run_in_executor(None, self.speaker_identifier.identify, audio)
            segments, speaker = await asyncio.gather(precise_task, speaker_task)
            return segments, speaker

        precise_task.cancel()
        logger.info(
            f"🔀 [{self.session_id}] 청크 안에서 화자 전환 감지 — {len(turns)}개 턴으로 분할 전사"
        )

        async def _one_turn(start: int, end: int, provisional: str | None):
            piece = audio[start:end]
            offset = start / REALTIME_SAMPLE_RATE
            # 턴 전체 오디오로 다시 판정한다 — 구간 단위보다 오디오가 많아 더 정확하고,
            # 여기서만 프로필을 갱신해 잘못된 배정이 지문을 오염시킬 여지를 줄인다.
            seg_task = loop.run_in_executor(
                None, self._transcribe, final_model, piece, PRECISE_BEAM_SIZE, self.initial_prompt
            )
            spk_task = loop.run_in_executor(None, self.speaker_identifier.identify, piece)
            segments, speaker = await asyncio.gather(seg_task, spk_task)
            for seg in segments:
                # 턴 안에서의 시각을 청크 기준으로 되돌린다 (청크→회의 기준 보정은 호출부가 담당)
                seg["start"] = round(seg["start"] + offset, 2)
                seg["end"] = round(seg["end"] + offset, 2)
                seg["speaker"] = speaker or provisional
            return segments, speaker, end - start

        results = await asyncio.gather(*(_one_turn(*t) for t in turns))

        merged: list[dict] = []
        spoken: dict[str, int] = {}
        for segments, speaker, samples in results:
            merged.extend(segments)
            if speaker:
                spoken[speaker] = spoken.get(speaker, 0) + samples
        merged.sort(key=lambda s: s["start"])
        dominant = max(spoken, key=spoken.get) if spoken else None
        return merged, dominant

    async def process_chunk(self, audio: np.ndarray, offset_sec: float) -> dict:
        """
        확정 전사(Precise)와 화자 식별을 병렬로 실행.
        잠정 텍스트는 maybe_stream_partial()이 이미 흘려보냈으므로 여기선 확정본만 만든다.
        신뢰도 낮은 세그먼트(confident=False)는 호출 측(모순 감지 엔진)에서
        경고를 보류하고 다음 신호를 기다리는 판단 근거로 사용.
        """
        loop = asyncio.get_event_loop()
        started = time.monotonic()
        self._observe_audio_quality(audio)
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
            precise_segments, speaker_label = await self._transcribe_with_speakers(
                audio, precise_task, final_model
            )
        else:
            precise_segments = await precise_task
            speaker_label = None

        latency_sec = round(time.monotonic() - started, 2)
        self._apply_offset_and_confidence(precise_segments, offset_sec)
        # 화자 분할 경로는 세그먼트마다 이미 speaker를 넣어뒀다. 나머지 경로만 일괄 배정.
        if speaker_label is not None:
            for seg in precise_segments:
                seg.setdefault("speaker", speaker_label)

        if self.recorder is not None:
            # NAS 위 디스크 쓰기가 이벤트 루프(다른 회의의 실시간 스트리밍 포함)를 막지 않게 executor로.
            # speaker를 함께 넘겨 각자 PC 모드에서 참가자별 트랙을 따로 남기게 한다
            # (믹스본은 목소리가 겹쳐 있어 회의 후 재전사에 쓸 수 없음).
            await loop.run_in_executor(
                None, self.recorder.add_chunk, audio, precise_segments, offset_sec, speaker_label
            )

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

    def _observe_audio_quality(self, audio: np.ndarray) -> None:
        """청크의 발화/배경을 갈라 감시기에 넘긴다. 판단은 감시기가 한다."""
        try:
            spans = get_speech_timestamps(
                audio, VadOptions(min_silence_duration_ms=REALTIME_SILENCE_MS),
                sampling_rate=REALTIME_SAMPLE_RATE,
            )
            mask = np.zeros(len(audio), dtype=bool)
            for span in spans:
                mask[span["start"]:span["end"]] = True
            self.audio_quality.observe(audio, mask)
        except Exception:
            # 품질 감시가 전사를 막으면 본말이 전도된다 — 실패해도 조용히 넘어간다
            logger.exception("⚠️ 오디오 품질 관찰 실패 — 전사는 계속 진행")

    def pop_audio_quality_warning(self) -> dict | None:
        """낼 경고가 있으면 한 번만 준다. 호출부가 클라이언트로 보낸다."""
        try:
            return self.audio_quality.check()
        except Exception:
            logger.exception("⚠️ 오디오 품질 판정 실패 — 경고 생략")
            return None

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

        buffer = self._materialize_buffer()
        loop = asyncio.get_event_loop()
        # 전사와 화자 판정을 병렬로 — 순차로 돌리면 임베딩 시간만큼 자막이 늦어진다
        # (process_chunk의 확정 경로와 같은 구조).
        segments, speaker = await asyncio.gather(
            loop.run_in_executor(None, self._transcribe, self.fast_model, buffer, FAST_BEAM_SIZE),
            self._partial_speaker(buffer),
        )
        # 주기는 전사가 '끝난' 시점부터 잰다. 시작 시점에 찍으면 전사가 주기보다
        # 오래 걸릴 때 끝나자마자 다음 잠정이 곧바로 돌아 확정 전사가 굶는다
        # (실측: 잠정이 워커를 독점해 전사 큐가 포화되고 오디오 프레임이 버려짐).
        self._last_partial_at = time.monotonic()
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
            # 잠정 화자 — 확정본이 도착하면 덮어써진다. 프론트는 이 값을 '추정'으로
            # 다뤄야 한다(확정 세그먼트의 speaker와 달리 바뀔 수 있음).
            "speaker": speaker,
        }

    async def _partial_speaker(self, buffer: np.ndarray) -> str | None:
        """
        지금 말하고 있는 사람을 버퍼 끝부분 목소리로 판정.

        확정 청크를 기다리지 않는 이유: 화자 식별에 침묵이 필요한 게 아니라
        우리가 청크를 침묵으로 끊고 있을 뿐이다. 임베딩 비교는 1초 이상 오디오면
        언제든 가능하므로, 잠정 자막에도 화자를 실시간으로 붙일 수 있다.
        프로필은 갱신하지 않는다(update_profile=False) — 1초마다 이동 평균을 돌리면
        잘못 배정된 구간이 목소리 지문을 빠르게 오염시킨다.
        """
        if self.fixed_speaker is not None:
            return self.fixed_speaker            # 각자 PC 모드 — 판정 자체가 불필요
        if self.speaker_identifier is None:
            return None

        tail_samples = int(REALTIME_PARTIAL_SPEAKER_TAIL_SEC * REALTIME_SAMPLE_RATE)
        tail = buffer[-tail_samples:] if len(buffer) > tail_samples else buffer
        if len(tail) < _MIN_PARTIAL_SPEAKER_SAMPLES:
            return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.speaker_identifier.identify(tail, update_profile=False)
        )
