"""
화자분리는 원본 오디오로, 전사만 DeepFilterNet으로 향상된 오디오로 하는
하이브리드 방식을 시험한다. 고역통과 필터도 DeepFilterNet도 회의 전체
오디오를 바꿔서 화자분리까지 다시 돌리면 화자가 쪼개져 붕괴했다(IDEAS.md
#8) — refine_service.py의 `transcribe_audio_file` 훅(2026-09-08 추가)으로
그 문제를 우회할 수 있는지 확인한다.

원본 회의 폴더는 건드리지 않는다 — 복사본(__hybrid 접미사)에서만 향상·재분석한다.

사용법:
  python try_hybrid_denoise.py \
      --meeting 8b5f84b7-5e29-46f5-bb67-158980a5f352_20260805-064739 \
      --script scripts/retention_meeting.txt \
      --dfn-python ~/dfn_venv/bin/python
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

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


def make_test_meeting(base_meeting: str, dfn_python: str) -> str:
    test_id = f"{base_meeting}__hybrid"
    test_dir = os.path.join(MEETINGS_DIR, test_id)
    base_dir = os.path.join(MEETINGS_DIR, base_meeting)
    if os.path.isdir(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    for name in os.listdir(base_dir):
        src = os.path.join(base_dir, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(test_dir, name))

    audio_path = os.path.join(test_dir, "audio.wav")           # 화자분리용 — 원본 그대로
    denoised_path = os.path.join(test_dir, "audio_denoised.wav")  # 전사용 — 향상본
    enhance_script = os.path.join(_HERE, "scripts", "dfn_enhance.py")
    out = sh(f"{dfn_python} {enhance_script} {audio_path} {denoised_path}")
    print(f"  {out.strip()}")
    if not os.path.isfile(denoised_path):
        raise SystemExit("❌ DeepFilterNet 향상 실패 — 위 에러 확인")

    meta_path = os.path.join(test_dir, "transcript.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    realtime = meta.get("realtime_segments")
    if realtime:
        meta["segments"] = realtime
        meta.pop("realtime_segments", None)
    meta.pop("refined", None)
    meta.pop("refined_at", None)
    meta["transcribe_audio_file"] = "audio_denoised.wav"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return test_id


def refine(meeting_id: str) -> None:
    sh(f"curl -s -X POST 'http://localhost:8002/api/meetings/{meeting_id}/refine?force=1'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--dfn-python", required=True,
                     help="격리 venv의 python 경로 (예: ~/dfn_venv/bin/python)")
    args = ap.parse_args()

    dfn_python = os.path.expanduser(args.dfn_python)
    script_abs = os.path.abspath(args.script)

    print("기준(원본) cpCER:")
    print(sh(f"cd {_HERE} && python meeteval_score.py --meetings {args.meeting}:{script_abs}"))

    print("\n=== 하이브리드(화자분리=원본 / 전사=향상본) 회의 준비 중 ===")
    test_id = make_test_meeting(args.meeting, dfn_python)
    print(f"  재분석 요청: {test_id}")
    refine(test_id)
    time.sleep(2)

    print("\n==================== 결과 ====================")
    print(sh(f"cd {_HERE} && python meeteval_score.py --meetings {test_id}:{script_abs}"))

    print(f"정리하려면: rm -rf {os.path.join(MEETINGS_DIR, test_id)}")


if __name__ == "__main__":
    main()
