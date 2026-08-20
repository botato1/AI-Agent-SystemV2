"""
회의 **중에** 오디오 상태를 지켜보다가 인식이 무너질 조건이면 경고한다.

왜 필요한가 (2026-08-05 실측):
  대본까지 준비해 5인 모의 회의를 녹음했는데 CER이 31.8%로 나왔다(평소 6% 수준).
  원인을 찾는 데 한 시간 넘게 걸렸고, 결국 **배경 소음**이었다 —
  SNR이 잘 나온 회의의 18.9dB에서 8.8dB로 떨어져 있었다.

  그런데 그걸 **회의가 끝난 뒤에** 알았다. 그때는 이미 늦다. 녹음을 다시 하려면
  다섯 명을 또 모아야 한다.

  마이크를 옮기거나 창문을 닫는 건 **회의 시작 20초 안에 알려주면 할 수 있는 일**이다.
  그래서 이 감시는 사후 보고가 아니라 **초반 경고**를 목표로 한다.

무엇을 보는가:
  SNR      — 말할 때와 안 할 때의 음량 비. **이게 가장 치명적이다**(실측된 실패 원인)
  발화 음량 — 너무 작으면 마이크가 멀거나 입력이 낮다
  클리핑   — 너무 커서 파형이 잘리면 목소리 특징이 뭉개진다
  무발화   — 소리가 아예 안 들어오면 마이크가 안 잡힌 것이다

⚠️ 문턱은 잘 나온 회의 1건과 나쁜 회의 1건, **표본 두 개로 정했다.** 잠정값이다.
   오경보가 잦으면(멀쩡한 회의에 경고가 뜨면) 사람들이 무시하게 되므로,
   확실히 나쁠 때만 뜨도록 보수적으로 잡았다. 표본이 쌓이면 조정할 것.
"""
import numpy as np

from ..core.config import (
    logger,
    REALTIME_SAMPLE_RATE,
    AUDIO_WARN_MIN_SPEECH_SEC,
    AUDIO_WARN_SNR_DB,
    AUDIO_WARN_SPEECH_RMS,
    AUDIO_WARN_CLIP_RATIO,
    AUDIO_WARN_NO_SPEECH_SEC,
)


class AudioQualityMonitor:
    """
    청크가 확정될 때마다 통계를 쌓아두고, 판단할 만큼 모이면 경고를 한 번 낸다.

    **같은 경고를 반복하지 않는다.** 회의 내내 같은 말이 계속 뜨면 사람들이 무시하게
    되고, 그러면 정작 중요한 순간에도 안 보게 된다. 조건이 해소됐다가 다시 나빠지면
    그때 다시 알린다.
    """

    def __init__(self):
        self._speech_energy = 0.0     # 제곱합 — 나중에 RMS로 환산
        self._speech_samples = 0
        self._background_energy = 0.0
        self._background_samples = 0
        self._clipped = 0
        self._total_samples = 0
        self._silent_streak_sec = 0.0
        self._sent: set[str] = set()

    def observe(self, audio: np.ndarray, speech_mask: np.ndarray | None = None) -> None:
        """
        청크 하나를 관찰한다. speech_mask는 발화 구간 표시(없으면 전부 발화로 본다).

        VAD를 여기서 다시 돌리지 않는다 — 실시간 경로가 청크를 자를 때 이미 돌렸고,
        같은 일을 두 번 하면 확정 자막이 그만큼 늦어진다.
        """
        if not len(audio):
            return
        self._total_samples += len(audio)
        self._clipped += int((np.abs(audio) > 0.99).sum())

        if speech_mask is None or not speech_mask.any():
            speech, background = audio, np.empty(0, dtype=audio.dtype)
        else:
            speech, background = audio[speech_mask], audio[~speech_mask]

        if len(speech):
            self._speech_energy += float((speech.astype(np.float64) ** 2).sum())
            self._speech_samples += len(speech)
        if len(background):
            self._background_energy += float((background.astype(np.float64) ** 2).sum())
            self._background_samples += len(background)

        # 발화가 하나도 없는 청크가 이어지면 마이크가 안 잡히는 것일 수 있다
        chunk_sec = len(audio) / REALTIME_SAMPLE_RATE
        if not len(speech) or self._rms(self._speech_energy, self._speech_samples) < 1e-4:
            self._silent_streak_sec += chunk_sec
        else:
            self._silent_streak_sec = 0.0

    @staticmethod
    def _rms(energy: float, samples: int) -> float:
        return float(np.sqrt(energy / samples)) if samples else 0.0

    @property
    def speech_sec(self) -> float:
        return self._speech_samples / REALTIME_SAMPLE_RATE

    def stats(self) -> dict:
        speech_rms = self._rms(self._speech_energy, self._speech_samples)
        background_rms = self._rms(self._background_energy, self._background_samples)
        snr = (
            20 * float(np.log10(speech_rms / background_rms))
            if speech_rms > 0 and background_rms > 1e-6 else None
        )
        return {
            "speech_rms": round(speech_rms, 4),
            "background_rms": round(background_rms, 4),
            "snr_db": round(snr, 1) if snr is not None else None,
            "clip_ratio": round(self._clipped / max(self._total_samples, 1), 5),
            "speech_sec": round(self.speech_sec, 1),
        }

    def check(self) -> dict | None:
        """
        지금까지 관찰한 것으로 경고를 낼지 판단한다. 낼 것이 없으면 None.

        경고 문구는 **무엇을 하면 되는지**까지 말한다 — "음질이 나쁩니다"만으로는
        사용자가 할 수 있는 게 없다.
        """
        # 마이크가 아예 안 잡히는 건 판단에 오래 걸릴 이유가 없다 — 바로 알린다
        if self._silent_streak_sec >= AUDIO_WARN_NO_SPEECH_SEC:
            return self._emit(
                "no_speech", "error",
                f"{int(self._silent_streak_sec)}초 동안 소리가 들어오지 않습니다. "
                "마이크가 선택돼 있는지, 음소거가 아닌지 확인해주세요.",
            )

        # 나머지는 판단할 만큼 말이 쌓여야 한다. 몇 초로 단정하면 오경보가 난다.
        if self.speech_sec < AUDIO_WARN_MIN_SPEECH_SEC:
            return None

        stats = self.stats()

        if stats["clip_ratio"] > AUDIO_WARN_CLIP_RATIO:
            return self._emit(
                "clipping", "warning",
                "소리가 너무 크게 들어와 일부가 잘리고 있습니다. "
                "마이크 입력 크기를 낮추거나 조금 떨어져 주세요.",
                stats,
            )

        if stats["snr_db"] is not None and stats["snr_db"] < AUDIO_WARN_SNR_DB:
            return self._emit(
                "low_snr", "warning",
                f"주변 소음에 비해 목소리가 작습니다(SNR {stats['snr_db']}dB). "
                "인식 정확도가 크게 떨어질 수 있어요. "
                "마이크를 가까이 하거나 에어컨·창문 등 소음원을 줄여주세요.",
                stats,
            )

        if stats["speech_rms"] < AUDIO_WARN_SPEECH_RMS:
            return self._emit(
                "low_volume", "warning",
                "목소리가 작게 들어오고 있습니다. "
                "마이크를 가까이 하거나 입력 크기를 올려주세요.",
                stats,
            )

        # 나빴다가 좋아졌으면 다음에 다시 나빠질 때 알릴 수 있게 표시를 지운다
        self._sent -= {"low_snr", "low_volume", "clipping"}
        return None

    def _emit(self, code: str, level: str, message: str, stats: dict | None = None) -> dict | None:
        if code in self._sent:
            return None            # 같은 경고를 반복하면 사람들이 무시하게 된다
        self._sent.add(code)
        logger.warning(f"🔊 오디오 품질 경고({code}): {message}")
        return {
            "type": "audio_quality",
            "level": level,
            "code": code,
            "message": message,
            **(stats or self.stats()),
        }
