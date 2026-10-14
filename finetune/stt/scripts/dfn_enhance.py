"""
DeepFilterNet으로 오디오 하나를 향상시킨다. **격리된 venv 안에서만** 실행할 것 —
stt 서버 코드(pyannote/faster-whisper 등)를 전혀 import하지 않는다. 이게 이
스크립트가 존재하는 이유다: DeepFilterNet은 numpy를 구버전으로 강제해서 공유
venv에 같이 두면 서버가 깨진다(IDEAS.md #8 참고).

DeepFilterNet 0.5.6(마지막 릴리스, PyPI 최신)은 `torchaudio.backend.common`의
`AudioMetaData`를 import 시점에 요구하는데, 이 API는 최근 torchaudio(2.1+
계열, aarch64 CPU 인덱스에서 설치 가능한 최소 버전이 이미 여기 해당)에서
제거됐다. 우리는 이 타입을 실제로 쓰지 않으므로(오디오 입출력은 직접
scipy로 한다) 임포트만 통과하도록 더미로 채워 넣는다.

DeepFilterNet은 48kHz로 동작한다. 우리 회의 녹음은 16kHz라, 향상 후 다시
16kHz로 리샘플해 저장한다(3배수라 정수 비율로 깔끔하게 떨어진다).

사용법 (격리 venv 안에서):
  python dfn_enhance.py 입력.wav 출력.wav
"""
import sys
import types


def _stub_torchaudio_backend() -> None:
    backend_mod = types.ModuleType("torchaudio.backend")
    common_mod = types.ModuleType("torchaudio.backend.common")

    class AudioMetaData:  # df.io는 타입 힌트로만 쓴다 — 실제 값은 안 씀
        pass

    common_mod.AudioMetaData = AudioMetaData
    backend_mod.common = common_mod
    sys.modules.setdefault("torchaudio.backend", backend_mod)
    sys.modules.setdefault("torchaudio.backend.common", common_mod)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용법: python dfn_enhance.py 입력.wav 출력.wav")
    inp, outp = sys.argv[1], sys.argv[2]

    import numpy as np
    import torch
    from scipy.io import wavfile
    from scipy.signal import resample_poly

    _stub_torchaudio_backend()
    from df.enhance import enhance, init_df

    model, df_state, _ = init_df()
    model_sr = df_state.sr()

    orig_sr, orig = wavfile.read(inp)
    mono = orig.mean(axis=1) if orig.ndim > 1 else orig
    x = mono.astype(np.float64)
    if orig.dtype.kind == "i":
        x = x / np.iinfo(orig.dtype).max

    if orig_sr != model_sr:
        from math import gcd
        g = gcd(orig_sr, model_sr)
        x = resample_poly(x, up=model_sr // g, down=orig_sr // g)

    audio_t = torch.from_numpy(x).float().unsqueeze(0)  # [1, T]
    enhanced = enhance(model, df_state, audio_t)

    y = enhanced.detach().cpu().numpy()
    if y.ndim > 1:
        y = y.mean(axis=0)

    target_sr = 16000
    if model_sr != target_sr:
        assert model_sr % target_sr == 0, f"정수비가 아닌 리샘플: {model_sr} -> {target_sr}"
        y = resample_poly(y, up=1, down=model_sr // target_sr)

    if orig.dtype.kind == "i":
        scale = np.iinfo(orig.dtype).max
        y_out = np.clip(y * scale, -scale - 1, scale).astype(orig.dtype)
    else:
        y_out = y.astype(orig.dtype)

    wavfile.write(outp, target_sr, y_out)
    print(f"완료: {outp} ({len(y_out) / target_sr:.1f}초, {target_sr}Hz)")


if __name__ == "__main__":
    main()
