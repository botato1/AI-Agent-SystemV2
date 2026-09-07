"""
DeepFilterNet으로 오디오 하나를 향상시킨다. **격리된 venv 안에서만** 실행할 것 —
stt 서버 코드(pyannote/faster-whisper 등)를 전혀 import하지 않는다. 이게 이
스크립트가 존재하는 이유다: DeepFilterNet은 numpy를 구버전으로 강제해서 공유
venv에 같이 두면 서버가 깨진다(IDEAS.md #8 참고).

DeepFilterNet은 48kHz로 동작한다. 우리 회의 녹음은 16kHz라, 향상 후 다시
16kHz로 리샘플해 저장한다(3배수라 정수 비율로 깔끔하게 떨어진다).

사용법 (격리 venv 안에서):
  python dfn_enhance.py 입력.wav 출력.wav
"""
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용법: python dfn_enhance.py 입력.wav 출력.wav")
    inp, outp = sys.argv[1], sys.argv[2]

    from df.enhance import enhance, init_df, load_audio

    model, df_state, _ = init_df()
    audio, _ = load_audio(inp, sr=df_state.sr())
    enhanced = enhance(model, df_state, audio)

    y = enhanced.detach().cpu().numpy() if hasattr(enhanced, "detach") else np.asarray(enhanced)
    if y.ndim > 1:
        y = y.mean(axis=0)

    model_sr = df_state.sr()
    target_sr = 16000
    if model_sr != target_sr:
        # 48000 -> 16000은 정확히 1/3 비율
        assert model_sr % target_sr == 0, f"정수비가 아닌 리샘플: {model_sr} -> {target_sr}"
        y = resample_poly(y, up=1, down=model_sr // target_sr)

    # 원본 dtype(대개 int16)에 맞춰 저장 — 우리 파이프라인이 기대하는 형식
    orig_sr, orig = wavfile.read(inp)
    if orig.dtype.kind == "i":
        scale = np.iinfo(orig.dtype).max
        y_out = np.clip(y * scale, np.iinfo(orig.dtype).min, scale).astype(orig.dtype)
    else:
        y_out = y.astype(orig.dtype)

    wavfile.write(outp, target_sr, y_out)
    print(f"완료: {outp} ({len(y_out) / target_sr:.1f}초, {target_sr}Hz)")


if __name__ == "__main__":
    main()
