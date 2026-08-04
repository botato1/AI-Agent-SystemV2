"""
저장된 회의를 **실제 재분석 경로로 다시 돌릴 수 있는 상태**로 되돌린다.

왜 필요한가:
  ① refine은 이미 refined=true면 건너뛴다. 알고리즘을 고친 뒤 같은 회의로 다시
     재보려면 그 표시를 지워야 한다.
  ② refine은 segments를 정밀본으로 **교체**한다(원본은 realtime_segments에 보존).
     지우지 않고 또 돌리면 이전 재분석 결과 위에 덮어써서, 무엇과 비교하는지가
     흐려진다. 실시간 결과를 다시 segments로 되돌려 매번 같은 출발점에서 시작한다.
  ③ 회의 당시 등록돼 있지 않던 참석자가 있으면 profiles.npz에 그 사람이 없어서
     무슨 알고리즘을 써도 못 맞힌다(실측: 8/3 5인 회의의 profiles.npz에 3명뿐이라
     이준오·이승주가 애초에 후보에 없었다). --profiles-from-global로 현재 등록
     프로필을 넣어주면 "전원이 등록돼 있었다면" 조건에서 잴 수 있다.

바꾸기 전에 원본을 .bak으로 남긴다. 되돌리려면 .bak을 다시 덮어쓰면 된다.

사용법:
  python prepare_refine_rerun.py --meeting <회의ID> --profiles-from-global
  curl -X POST http://127.0.0.1:8002/api/meetings/<회의ID>/refine
"""
import argparse
import json
import os
import shutil
import sys

import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR  # noqa: E402
from stt.services.profile_store import GlobalProfileStore  # noqa: E402


def backup(path: str) -> None:
    if os.path.isfile(path) and not os.path.isfile(path + ".bak"):
        shutil.copy2(path, path + ".bak")
        print(f"  백업: {os.path.basename(path)}.bak")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--profiles-from-global", action="store_true",
                        help="profiles.npz를 현재 전역 등록 프로필로 다시 만든다")
    parser.add_argument("--names", nargs="*", default=None,
                        help="넣을 참석자 이름. 생략하면 등록된 전원")
    args = parser.parse_args()

    meeting_dir = os.path.join(MEETINGS_DIR, args.meeting)
    if not os.path.isdir(meeting_dir):
        raise SystemExit(f"❌ 회의 없음: {meeting_dir}")

    meta_path = os.path.join(meeting_dir, "transcript.json")
    backup(meta_path)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    realtime = meta.get("realtime_segments")
    if realtime:
        # 이전 재분석이 남긴 결과를 걷어내고 실시간 결과를 출발점으로 되돌린다
        meta["segments"] = realtime
        meta.pop("realtime_segments", None)
        print(f"  segments를 실시간 결과로 복원 ({len(realtime)}개)")
    meta.pop("refined", None)
    meta.pop("refined_at", None)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("  refined 표시 제거 — 다시 재분석 가능")

    if args.profiles_from_global:
        profiles_path = os.path.join(meeting_dir, "profiles.npz")
        before = list(np.load(profiles_path).files) if os.path.isfile(profiles_path) else []
        backup(profiles_path)

        store = GlobalProfileStore()
        names = args.names or store.list_names()
        profiles = store.load(names)
        if not profiles:
            raise SystemExit("❌ 전역 등록 프로필이 없다")
        np.savez(profiles_path, **profiles)

        added = [n for n in profiles if n not in before]
        print(f"  profiles.npz: {len(before)}명 → {len(profiles)}명 ({', '.join(profiles)})")
        if added:
            print(f"  추가됨: {', '.join(added)}")

    print(f"\n이제 재분석을 돌리면 된다:")
    print(f"  curl -X POST http://127.0.0.1:8002/api/meetings/{args.meeting}/refine")


if __name__ == "__main__":
    main()
