"""
저역(에어컨/공조기 추정) 소음이 심한 회의에 **고역통과 필터 하나만** 걸어보고
cpCER이 실제로 좋아지는지 확인한다. 새 라이브러리 설치 없이 scipy만 쓴다
(DeepFilterNet/pyrnnoise는 설치 단계에서 막혔었다 — IDEAS.md #8 참고).

절대 원본 회의 폴더를 건드리지 않는다 — 복사본을 새 회의ID로 만들어 그 안에서만
필터링·재분석한다.

사용법:
  python try_highpass_denoise.py --meeting 8b5f84b7-5e29-46f5-bb67-158980a5f352_20260805-064739 \
      --script scripts/retention_meeting.txt --cutoffs 150 200 250
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR  # noqa: E402


def sh(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠️ 명령 실패(exit {r.returncode}): {cmd}", file=sys.stderr)
        if r.stderr:
            print(r.stderr, file=sys.stderr)
    return r.stdout


def highpass(wav_path: str, out_path: str, cutoff_hz: float) -> None:
    sr, data = wavfile.read(wav_path)
    dtype = data.dtype
    mono = data.mean(axis=1) if data.ndim > 1 else data
    x = mono.astype(np.float64)
    scale = 1.0
    if dtype.kind == "i":
        scale = np.iinfo(dtype).max
        x = x / scale
    sos = butter(4, cutoff_hz, btype="highpass", fs=sr, output="sos")
    y = sosfiltfilt(sos, x)
    if dtype.kind == "i":
        y = np.clip(y * scale, np.iinfo(dtype).min, np.iinfo(dtype).max).astype(dtype)
    else:
        y = y.astype(dtype)
    wavfile.write(out_path, sr, y)


def make_test_meeting(base_meeting: str, cutoff_hz: float) -> str:
    test_id = f"{base_meeting}__hpf{int(cutoff_hz)}"
    test_dir = os.path.join(MEETINGS_DIR, test_id)
    base_dir = os.path.join(MEETINGS_DIR, base_meeting)
    if os.path.isdir(test_dir):
        shutil.rmtree(test_dir)
    # copytree는 copy_function을 줘도 디렉토리 자체의 stat까지 복사하려다
    # NAS에서 PermissionError로 죽는다(prepare_refine_rerun.py의 backup()과 같은
    # 함정) — 새 디렉토리를 만들고 파일만 내용으로 복사한다.
    os.makedirs(test_dir)
    for name in os.listdir(base_dir):
        src = os.path.join(base_dir, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(test_dir, name))
    for stray in ("profiles.npz.bak", "transcript.json.bak"):
        p = os.path.join(test_dir, stray)
        if os.path.isfile(p):
            os.remove(p)

    audio_path = os.path.join(test_dir, "audio.wav")
    highpass(audio_path, audio_path, cutoff_hz)

    meta_path = os.path.join(test_dir, "transcript.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    realtime = meta.get("realtime_segments")
    if realtime:
        meta["segments"] = realtime
        meta.pop("realtime_segments", None)
    meta.pop("refined", None)
    meta.pop("refined_at", None)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return test_id


def refine(meeting_id: str) -> None:
    sh(f"curl -s -X POST 'http://localhost:8002/api/meetings/{meeting_id}/refine?force=1'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--cutoffs", nargs="+", type=float, default=[150, 200, 250])
    args = ap.parse_args()

    script_abs = os.path.abspath(args.script)

    print(f"기준(원본) cpCER:")
    print(sh(f"cd {_HERE} && python meeteval_score.py "
             f"--meetings {args.meeting}:{script_abs}"))

    test_ids = []
    for cutoff in args.cutoffs:
        print(f"\n=== 고역통과 {cutoff:.0f}Hz 회의 준비 중 ===")
        test_id = make_test_meeting(args.meeting, cutoff)
        test_ids.append((cutoff, test_id))
        print(f"  재분석 요청: {test_id}")
        refine(test_id)
        time.sleep(2)

    print("\n\n==================== 결과 ====================")
    pairs = " ".join(f"{tid}:{script_abs}" for _, tid in test_ids)
    print(sh(f"cd {_HERE} && python meeteval_score.py --meetings {pairs}"))

    print("정리하려면: rm -rf " + " ".join(
        os.path.join(MEETINGS_DIR, tid) for _, tid in test_ids))


if __name__ == "__main__":
    main()
