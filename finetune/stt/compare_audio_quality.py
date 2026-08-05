"""
두 회의 녹음의 **음질을 나란히 비교**한다. "오디오가 어렵다"를 구체적인 수치로 바꾸는 도구.

왜 필요한가:
  전사가 나쁠 때 "오디오가 어렵다"까지는 알아내도, 그것만으로는 다시 녹음할 때
  **무엇을 고쳐야 하는지** 알 수 없다. 마이크를 가까이 해야 하는지, 조용한 곳으로
  옮겨야 하는지, 천천히 말해야 하는지가 다 다른 처방이다.

  잘 나왔던 녹음과 나란히 재면 "무엇이 달랐는지"가 드러난다.

재는 것과 그 뜻:
  발화 비율   — 전체 중 사람이 말한 시간. 낮으면 침묵·잡음이 많다는 뜻
  발화 RMS    — 말할 때의 음량. 낮으면 마이크에서 멀다
  배경 RMS    — 말 안 할 때의 음량. 높으면 주변이 시끄럽다
  SNR         — 위 둘의 비. **이게 낮은 것이 전사를 가장 크게 망가뜨린다**
  글자/초     — 말하는 속도. 높으면 빨리 읽어 발음이 뭉갠다
  고역 비율   — 고주파 에너지 비중. 낮으면 소리가 먹먹하다(멀거나 가려짐)
  클리핑      — 음량이 넘쳐 파형 꼭대기가 잘린 비율

사용법:
  python compare_audio_quality.py --meetings <좋았던회의ID> <문제회의ID>
  python compare_audio_quality.py --meetings A B --chars 887 750
      (--chars로 각 회의의 대본 글자 수를 주면 말하기 속도까지 낸다)
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR  # noqa: E402


def analyze(path: str, script_chars: int | None) -> dict:
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    spans = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=300), sampling_rate=sr)
    speech_mask = np.zeros(len(audio), dtype=bool)
    for span in spans:
        speech_mask[span["start"]:span["end"]] = True

    speech, background = audio[speech_mask], audio[~speech_mask]
    speech_rms = float(np.sqrt((speech ** 2).mean())) if len(speech) else 0.0
    background_rms = float(np.sqrt((background ** 2).mean())) if len(background) else 0.0
    # SNR을 dB로. 배경이 0에 가까우면 무한대가 되므로 하한을 둔다.
    snr = 20 * np.log10(speech_rms / max(background_rms, 1e-6)) if speech_rms else 0.0

    # 고역 비율: 스펙트럼을 반으로 갈라 위쪽 에너지 비중. 멀거나 가려진 소리는 고역이 준다.
    if len(speech) > sr:
        spectrum = np.abs(np.fft.rfft(speech[:sr * 30] * np.hanning(min(len(speech), sr * 30))))
        half = len(spectrum) // 2
        high_ratio = float(spectrum[half:].sum() / max(spectrum.sum(), 1e-9))
    else:
        high_ratio = 0.0

    speech_sec = speech_mask.sum() / sr
    return {
        "duration": len(audio) / sr,
        "speech_ratio": speech_mask.mean(),
        "speech_rms": speech_rms,
        "background_rms": background_rms,
        "snr_db": snr,
        "high_ratio": high_ratio,
        "clip_pct": float((np.abs(audio) > 0.99).mean() * 100),
        "chars_per_sec": (script_chars / speech_sec) if script_chars and speech_sec else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--chars", nargs="*", type=int, default=None,
                        help="회의별 대본 글자 수(순서 맞춰). 주면 말하기 속도를 낸다")
    args = parser.parse_args()

    results = []
    for i, meeting in enumerate(args.meetings):
        path = os.path.join(MEETINGS_DIR, meeting, args.audio)
        if not os.path.isfile(path):
            print(f"⚠️ 오디오 없음: {meeting}")
            continue
        chars = args.chars[i] if args.chars and i < len(args.chars) else None
        results.append((meeting, analyze(path, chars)))

    if not results:
        raise SystemExit("❌ 분석할 오디오가 없다")

    rows = [
        ("길이(초)", "duration", "{:.0f}"),
        ("발화 비율", "speech_ratio", "{:.0%}"),
        ("발화 RMS", "speech_rms", "{:.4f}"),
        ("배경 RMS", "background_rms", "{:.4f}"),
        ("SNR(dB)", "snr_db", "{:.1f}"),
        ("고역 비율", "high_ratio", "{:.3f}"),
        ("클리핑(%)", "clip_pct", "{:.2f}"),
        ("글자/초", "chars_per_sec", "{:.2f}"),
    ]
    width = 16
    print(f"{'':12s}" + "".join(f"{m[:width - 1]:>{width}s}" for m, _r in results))
    print("-" * (12 + width * len(results)))
    for label, key, fmt in rows:
        cells = []
        for _m, r in results:
            cells.append(fmt.format(r[key]) if r[key] is not None else "-")
        print(f"{label:12s}" + "".join(f"{c:>{width}s}" for c in cells))

    print("\n읽는 법 — 문제 회의가 잘 나온 회의보다:")
    print("  SNR이 낮다      → 주변이 시끄럽거나 마이크가 멀다. **전사에 가장 치명적**")
    print("  발화 RMS가 낮다 → 마이크에서 멀다. 가까이 하거나 입력을 올릴 것")
    print("  배경 RMS가 높다 → 에어컨·팬·복도 소음. 조용한 곳으로")
    print("  고역 비율이 낮다 → 소리가 먹먹하다. 마이크가 가려졌거나 너무 멀다")
    print("  글자/초가 높다  → 빨리 말해 발음이 뭉갰다. 천천히 읽을 것")
    print("\n차이가 다 작으면 음질이 아니라 **발음·겹침** 문제다 — 그건 수치로 안 잡힌다.")


if __name__ == "__main__":
    main()
