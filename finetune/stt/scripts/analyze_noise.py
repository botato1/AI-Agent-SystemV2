"""
회의 오디오의 소음 특성을 빠르게 진단한다: 노이즈 플로어, 대략적인 SNR,
클리핑 비율, 주파수 대역별 에너지 분포(저역 웅웅거림 vs 광대역 소음 vs 고역 히스).
비교 대상 회의(정상적으로 잘 나온 회의)를 같이 넣으면 상대 비교가 된다.

사용법:
  python analyze_noise.py meetings/8b5f84b7-.../audio.wav [meetings/ded1105f-.../audio.wav ...]
"""
import sys
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft


def analyze(path: str) -> None:
    sr, data = wavfile.read(path)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if data.dtype.kind == "i":
        data = data.astype(np.float64) / np.iinfo(data.dtype).max
    else:
        data = data.astype(np.float64)

    dur = len(data) / sr
    frame = int(sr * 0.03)
    hop = frame // 2
    n_frames = max(1, (len(data) - frame) // hop)
    rms = np.array([
        np.sqrt(np.mean(data[i * hop: i * hop + frame] ** 2) + 1e-12)
        for i in range(n_frames)
    ])
    rms_db = 20 * np.log10(rms + 1e-12)

    noise_floor_db = np.percentile(rms_db, 10)
    speech_level_db = np.percentile(rms_db, 90)
    snr_est = speech_level_db - noise_floor_db

    clip_ratio = np.mean(np.abs(data) > 0.99) * 100

    f, t, Z = stft(data, fs=sr, nperseg=2048)
    power = np.abs(Z) ** 2
    mean_power = power.mean(axis=1)

    def band_power(lo, hi):
        mask = (f >= lo) & (f < hi)
        return 10 * np.log10(mean_power[mask].sum() + 1e-12)

    low = band_power(0, 300)
    speech = band_power(300, 3400)
    high = band_power(3400, 8000)

    print(f"\n=== {path} ===")
    print(f"길이: {dur:.1f}초, 샘플레이트: {sr}Hz")
    print(f"노이즈 플로어(하위10%): {noise_floor_db:.1f} dB")
    print(f"발화 레벨(상위10%):   {speech_level_db:.1f} dB")
    print(f"추정 SNR:            {snr_est:.1f} dB")
    print(f"클리핑 비율:          {clip_ratio:.3f}%")
    print(f"대역 에너지  저역(0-300Hz): {low:.1f} dB / "
          f"음성대역(300-3400Hz): {speech:.1f} dB / "
          f"고역(3400-8000Hz): {high:.1f} dB")
    print(f"저역-음성대역 차:      {low - speech:+.1f} dB  (0에 가까우면 저역 소음이 심함)")

    # 무음(가장 조용한 프레임) 구간만 모아서 소음 자체의 주파수 특성을 본다.
    # 협대역 피크(예: 60Hz 전원 험)면 특정 주파수가 튀고,
    # 광대역(에어컨/팬)이면 넓게 퍼져서 뚜렷한 피크가 없다.
    quiet_thresh = np.percentile(rms_db, 20)
    quiet_frame_idx = np.where(rms_db <= quiet_thresh)[0]
    if len(quiet_frame_idx) > 0:
        quiet_power = power[:, np.clip(quiet_frame_idx, 0, power.shape[1] - 1)].mean(axis=1)
        low_mask = (f >= 20) & (f < 500)
        low_f = f[low_mask]
        low_p_db = 10 * np.log10(quiet_power[low_mask] + 1e-12)
        top5 = np.argsort(low_p_db)[-5:][::-1]
        peaks = ", ".join(f"{low_f[i]:.0f}Hz({low_p_db[i]:.1f}dB)" for i in top5)
        spread = low_p_db.max() - low_p_db.min()
        print(f"무음구간 20-500Hz 상위 피크: {peaks}")
        print(f"무음구간 20-500Hz 최대-최소 편차: {spread:.1f} dB "
              f"(크면=특정 주파수가 튐→협대역 험, 작으면=광대역 소음)")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        analyze(p)
