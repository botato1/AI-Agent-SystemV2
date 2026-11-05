"""
DeepFilterNet(격리 venv, `scripts/dfn_enhance.py`)으로 향상시킨 오디오가
cpCER을 실제로 개선하는지 확인한다. 고역통과 필터(150~250Hz)는 전부 악화로
끝났다(IDEAS.md #8, 화자가 5명→11~12명으로 쪼개짐) — F0 대역까지 잘라내서
화자 임베딩을 망가뜨린 것으로 추정된다. DeepFilterNet은 학습된 모델로 소음과
음성을 구분하므로 같은 문제가 없을 수 있다.

원본 회의 폴더는 건드리지 않는다 — 복사본(__dfn 접미사)에서만 향상·재분석한다.
DeepFilterNet 실행 자체는 격리 venv의 파이썬을 서브프로세스로 불러서 하므로,
이 스크립트는 평소 쓰는 stt_venv에서 그대로 돌리면 된다.

사용법:
  python try_deepfilternet_denoise.py \
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
    test_id = f"{base_meeting}__dfn"
    test_dir = os.path.join(MEETINGS_DIR, test_id)
    base_dir = os.path.join(MEETINGS_DIR, base_meeting)
    if os.path.isdir(test_dir):
        shutil.rmtree(test_dir)
    # os.makedirs + 파일별 copyfile — copytree(copy2)는 다른 사용자 소유 파일의
    # 메타데이터를 복사하려다 NAS에서 PermissionError로 죽는다.
    os.makedirs(test_dir)
    for name in os.listdir(base_dir):
        src = os.path.join(base_dir, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(test_dir, name))

    audio_path = os.path.join(test_dir, "audio.wav")
    enhance_script = os.path.join(_HERE, "scripts", "dfn_enhance.py")
    out = sh(f"{dfn_python} {enhance_script} {audio_path} {audio_path}.enhanced")
    print(f"  {out.strip()}")
    if not os.path.isfile(f"{audio_path}.enhanced"):
        raise SystemExit("❌ DeepFilterNet 향상 실패 — 위 에러 확인")
    os.replace(f"{audio_path}.enhanced", audio_path)

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
    ap.add_argument("--dfn-python", required=True,
                     help="격리 venv의 python 경로 (예: ~/dfn_venv/bin/python)")
    args = ap.parse_args()

    dfn_python = os.path.expanduser(args.dfn_python)
    script_abs = os.path.abspath(args.script)

    print("기준(원본) cpCER:")
    print(sh(f"cd {_HERE} && python meeteval_score.py --meetings {args.meeting}:{script_abs}"))

    print("\n=== DeepFilterNet 향상 회의 준비 중 (시간 걸림) ===")
    test_id = make_test_meeting(args.meeting, dfn_python)
    print(f"  재분석 요청: {test_id}")
    refine(test_id)
    time.sleep(2)

    print("\n==================== 결과 ====================")
    print(sh(f"cd {_HERE} && python meeteval_score.py --meetings {test_id}:{script_abs}"))

    print(f"정리하려면: rm -rf {os.path.join(MEETINGS_DIR, test_id)}")


if __name__ == "__main__":
    main()
