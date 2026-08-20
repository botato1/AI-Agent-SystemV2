"""
화자 타임라인 판정 방식 — **창별 독립 판정** vs **묶음 단위 판정**을 cpCER로 비교한다.

왜 필요한가 (2026-08-20, NEXT.md #3):
  지금(build_speaker_timeline)은 창(1.5초) 하나하나가 등록 프로필과 독립적으로
  경쟁하고, 이웃 3창 다수결로만 흔들림을 보정한다. 경계선에 있는 사람은 여러 창이
  몰려서 틀리면 다수결로도 못 되돌린다 — 8b5f84b7의 이승주 2발화가 어디로
  붙느냐에 따라 cpCER이 56.60~70.80%로 14.2%p 흔들린 게 그 증상이다.

  build_speaker_timeline_clustered(speaker_timeline.py, 신규)는 회의 안에서
  비슷한 목소리끼리 먼저 묶고(그리디 병합, 상한=등록 인원수) 묶음 평균 임베딩으로
  딱 한 번만 판정한다. 개별 창의 노이즈가 묶음 전체를 못 뒤집을 것으로 기대하지만
  **가설일 뿐이다** — 클러스터링 자체가 잘못 묶으면(다른 두 사람을 하나로) 오히려
  새로운 실패 모드가 생긴다. 반드시 cpCER로 확인한 뒤 채택 여부를 정한다.

⚠️ EER만 보고 채택하지 말 것 — 파인튜닝 때 같은 함정에 걸렸다(EXPERIMENTS.md).
⚠️ 명단 밖 오수락도 같이 봐야 한다. 묶음이 판정을 더 확신 있게 만든다면, 명단 밖
   사람에게도 더 확신 있게(잘못) 이름을 붙일 위험이 있다 — 이 스크립트는 그건
   안 재므로, 채택 전에 sweep_speaker_floor.py 류로 별도 확인이 필요할 수 있다.

사용법:
  python probe_clustered_timeline.py \
      --meetings ded1105f-...:scripts/launch_plan_meeting.txt \
                 ba8f38c4-...:scripts/search_quality_meeting.txt \
                 8b5f84b7-...:scripts/retention_meeting.txt \
      --floors 0.50 0.55 0.60   # SPEAKER_CLUSTER_MERGE_FLOOR 스윕(선택, 기본 0.55만)
"""
import argparse
import os
import re
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def restart(clustered: bool, merge_floor: str) -> bool:
    sh("kill $(pgrep -f 'uvicorn stt.main:app') 2>/dev/null")
    time.sleep(5)
    env = f"SPEAKER_TIMELINE_CLUSTERED={'1' if clustered else '0'} SPEAKER_CLUSTER_MERGE_FLOOR={merge_floor}"
    subprocess.Popen(
        f"cd {os.path.join(_REPO_ROOT, 'backend', 'modules')} && "
        f"{env} nohup python -u -m uvicorn stt.main:app "
        f"--host 0.0.0.0 --port 8002 >> /tmp/stt.log 2>&1 &", shell=True,
    )
    for _ in range(40):
        time.sleep(5)
        if sh("curl -s -o /dev/null -w '%{http_code}' http://localhost:8002/docs") == "200":
            return True
    return False


def refine_and_score(meeting: str, script: str) -> dict:
    sh(f"cd {_HERE} && python prepare_refine_rerun.py --meeting {meeting} "
       f"--profiles-from-global 2>/dev/null")
    sh(f"curl -s -X POST 'http://localhost:8002/api/meetings/{meeting}/refine?force=1'")
    mt = sh(f"cd {_HERE} && python meeteval_score.py --meetings '{meeting}:{script}' 2>/dev/null")
    # 열 순서: cpCER, DI-cpCER, ORC-CER, 화자대가, cpWER
    row = re.search(re.escape(meeting[:38]) + r"\s*([\d.]+)%\s*([\d.]+)%\s*([\d.]+)%\s*([\d.]+)%", mt)
    if not row:
        return {}
    return {"cpcer": float(row.group(1)), "di_cpcer": float(row.group(2)),
            "orc": float(row.group(3)), "speaker_cost": float(row.group(4))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True, help="'회의ID:대본'")
    parser.add_argument("--floors", nargs="+", default=["0.55"],
                         help="SPEAKER_CLUSTER_MERGE_FLOOR 스윕값들 (묶음 판정 조건에서만 적용)")
    args = parser.parse_args()
    specs = [tuple(s.split(":", 1)) for s in args.meetings]

    conditions: list[tuple[str, bool, str]] = [("창별(기존)", False, "0.55")]
    conditions += [(f"묶음(floor={f})", True, f) for f in args.floors]

    rows: dict[str, dict[str, dict]] = {}
    for label, clustered, floor in conditions:
        print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
        if not restart(clustered, floor):
            print("  ❌ 서버가 안 뜬다 — 중단"); break
        rows[label] = {}
        for meeting, script in specs:
            r = refine_and_score(meeting, os.path.join(_HERE, script))
            if not r:
                print(f"  [{meeting[:38]}] ⚠️ 채점 실패"); continue
            rows[label][meeting] = r
            print(f"  [{meeting[:38]}] cpCER {r['cpcer']:.2f}%  화자대가 {r['speaker_cost']:.2f}%")

    print(f"\n{'=' * 78}\n요약 (cpCER, 낮을수록 좋음)\n{'=' * 78}")
    meetings = [m for m, _ in specs]
    print("조건".ljust(22) + "".join(m[:8].rjust(10) for m in meetings) + "평균".rjust(10))
    for label, per_meeting in rows.items():
        vals = [per_meeting.get(m, {}).get("cpcer") for m in meetings]
        cells = "".join(f"{v:9.2f}%" if v is not None else "     N/A" for v in vals)
        valid = [v for v in vals if v is not None]
        avg = f"{sum(valid) / len(valid):8.2f}%" if valid else "     N/A"
        print(label.ljust(22) + cells + avg)

    print()
    print("읽는 법")
    print("  '창별(기존)' 대비 '묶음'이 회의 3개 전부에서 일관되게 낮아야 채택 후보.")
    print("  한 회의만 좋아지면 그 회의 조건에 맞춘 것 — 채택하지 말 것.")
    print()
    print("⚠️ 여기서 좋아 보여도 명단 밖 오수락을 별도로 확인하기 전에는 배포 기본값을")
    print("   켜지 말 것(SPEAKER_TIMELINE_CLUSTERED 기본값은 0으로 둔 채 유지).")


if __name__ == "__main__":
    main()
