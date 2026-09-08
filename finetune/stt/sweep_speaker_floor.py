"""
절대 하한(SPEAKER_ABSOLUTE_FLOOR)을 **이득과 위험을 함께** 재며 훑는다.

왜 필요한가 (2026-08-13):
  짧은 발언이 옆 사람 발언에 흡수되는 원인을 단계별 추적으로 특정했다 —
  **타임라인이 그 구간을 "미상"으로 판정해서 턴을 못 나눈다.**
  그리고 미상이 되는 이유는 절대 하한이다: 창 단위 측정에서 이승주 0.275~0.34,
  김나연 0.277~0.30인데 하한이 0.35라 전부 걸러진다. 두 사람은 1등 정확도가
  84~100%인데도 그렇다.

  절대 유사도는 "누가 말했나"가 아니라 **"그 사람 프로필이 얼마나 좋은가"**를 잰다
  (문지수 0.53 / 김나연 0.30인데 둘 다 1등은 맞힌다). 공통 하한은 프로필이 약한
  사람만 조직적으로 걸러낸다.

⚠️ 그런데 하한을 낮추는 건 위험하다. 하한의 본래 임무는 **"등록된 누구와도 안 닮았으면
   이름을 붙이지 마라"**이고, 그게 무너지면 명단 밖 사람의 발언에 남의 이름이 붙는다.
   회의록에 없는 사람의 말이 남는 것이라 미상보다 나쁘다.
   실제로 전에 0.35→0.30으로 내렸다가 되돌린 적이 있다.

   **이 회의들은 참석자가 전원 등록돼 있어 그 위험이 측정되지 않는다.** 그래서 이
   도구는 두 조건을 함께 돌린다:

     A. 정상 — 참석자 전원이 후보. 이득(미상 감소, cpCER 개선)을 잰다
     B. 명단 밖 — 한 명을 **일부러 후보에서 빼고** 같은 오디오를 돌린다.
        그 사람 발언에 남의 이름이 붙으면 그게 오수락이다.

   **A만 보면 "낮출수록 좋다"가 나올 수밖에 없다.** B가 멈출 지점을 알려준다.

사용법:
  python sweep_speaker_floor.py --meeting <회의ID> --script scripts/xxx.txt \\
      --names 문지수 김나연 이승주 이준오 --holdout 이준오
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR  # noqa: E402
from evaluate_against_script import load_script, align  # noqa: E402

FLOORS = ["0.35", "0.30", "0.25", "0.20", "0.15"]


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def restart(floor: str, extra_env: str = "") -> bool:
    """서버를 지정한 설정으로 다시 띄운다. extra_env는 'K=V K2=V2' 형태."""
    sh("kill $(pgrep -f 'uvicorn stt.main:app') 2>/dev/null")
    time.sleep(5)
    subprocess.Popen(
        f"cd {os.path.join(_REPO_ROOT, 'backend', 'modules')} && "
        f"SPEAKER_ABSOLUTE_FLOOR={floor} {extra_env} nohup python -u -m uvicorn stt.main:app "
        f"--host 0.0.0.0 --port 8002 >> /tmp/stt.log 2>&1 &", shell=True,
    )
    for _ in range(40):
        time.sleep(5)
        if sh("curl -s -o /dev/null -w '%{http_code}' http://localhost:8002/docs") == "200":
            return True
    return False


def refine_with(meeting: str, names: list[str]) -> list[dict]:
    """후보를 names로 바꿔 재분석하고 결과 세그먼트를 돌려준다."""
    sh(f"cd {_REPO_ROOT} && python finetune/stt/prepare_refine_rerun.py --meeting {meeting} "
       f"--names {' '.join(names)} --profiles-from-global 2>/dev/null")
    sh(f"curl -s -X POST 'http://localhost:8002/api/meetings/{meeting}/refine?force=1'")
    path = os.path.join(MEETINGS_DIR, meeting, "transcript.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("segments") or []


def truth_spans(meeting: str, script_path: str, speaker: str) -> list[tuple[float, float]]:
    """대본+실시간 전사 정렬로 특정 화자의 발화 구간을 얻는다(make_truth_spans와 같은 방식).

    실시간 전사를 쓴다 — 재분석본은 조건마다 바뀌므로 정답이 흔들리면 안 된다.
    """
    path = os.path.join(MEETINGS_DIR, meeting, "transcript.json")
    with open(path, encoding="utf-8") as f:
        segs = sorted((json.load(f).get("realtime_segments") or []),
                      key=lambda s: s.get("start", 0))
    script = load_script(os.path.expanduser(script_path))
    out = []
    for line, idx in zip(script, align(script, segs)):
        if line["speaker"] != speaker or line["overlapped"] or not idx:
            continue
        out.append((segs[idx[0]]["start"] + 0.3, segs[idx[-1]]["end"] - 0.3))
    return [(s, e) for s, e in out if e - s >= 0.5]


def false_accepts(segments: list[dict], spans: list[tuple[float, float]]) -> tuple[int, int]:
    """(이름이 붙은 구간 수, 전체 구간 수). 명단 밖 화자는 전부 미상이어야 정상이다."""
    named = 0
    for start, end in spans:
        # 그 구간을 가장 많이 덮는 세그먼트의 라벨을 본다
        best, best_cover = None, 0.0
        for s in segments:
            cover = min(s["end"], end) - max(s["start"], start)
            if cover > best_cover:
                best, best_cover = s, cover
        if best is not None and best.get("speaker"):
            named += 1
    return named, len(spans)


def score(meeting: str, script: str) -> dict:
    mt = sh(f"cd {_HERE} && python meeteval_score.py --meetings '{meeting}:{script}' 2>/dev/null")
    ev = sh(f"cd {_REPO_ROOT} && python finetune/stt/evaluate_against_script.py "
            f"--meeting {meeting} --script finetune/stt/{script} 2>/dev/null")
    row = re.search(re.escape(meeting[:38]) + r"\s*([\d.]+)%\s*([\d.]+)%\s*([\d.]+)%\s*([\d.]+)%", mt)
    spk = re.search(r"화자 정확도: (\d+)/(\d+).*?오배정 (\d+), 미상 (\d+)", ev)
    if not (row and spk):
        return {}
    return {"cp": float(row.group(1)), "cost": float(row.group(4)),
            "correct": int(spk.group(1)), "total": int(spk.group(2)),
            "wrong": int(spk.group(3)), "missed": int(spk.group(4))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--script", required=True, help="finetune/stt 기준 상대경로")
    parser.add_argument("--names", nargs="+", required=True, help="실제 참석자 전원")
    parser.add_argument("--holdout", required=True, help="B조건에서 후보에서 뺄 사람")
    parser.add_argument("--floors", nargs="+", default=FLOORS,
                        help="잴 하한 값들. 확인 단계에서는 후보값과 기준선만 주면 빠르다")
    parser.add_argument("--extra-env", nargs="*", default=[],
                        help="서버에 함께 넘길 환경변수. 'K=V' 형태로 여러 개. "
                             "하한 외의 설정을 A/B 할 때 쓴다")
    args = parser.parse_args()
    floors = args.floors

    if args.holdout not in args.names:
        raise SystemExit(f"❌ --holdout({args.holdout})이 --names에 없다")
    spans = truth_spans(args.meeting, os.path.join(_HERE, args.script), args.holdout)
    if not spans:
        raise SystemExit(f"❌ {args.holdout}의 발화 구간을 못 찾았다 — 대본/회의가 맞는지 확인")
    print(f"명단 밖 시험 대상: {args.holdout} — 발화 구간 {len(spans)}개")

    rows = []
    for floor in floors:
        label = f"하한 {floor}" + (f"  [{' '.join(args.extra_env)}]" if args.extra_env else "")
        print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
        if not restart(floor, " ".join(args.extra_env)):
            print("  ❌ 서버가 안 뜬다 — 중단"); break

        print("  A) 참석자 전원 후보...")
        refine_with(args.meeting, args.names)
        a = score(args.meeting, args.script)
        if not a:
            print("  ⚠️ 채점 실패 — 건너뜀"); continue

        print(f"  B) {args.holdout} 제외...")
        segs_b = refine_with(args.meeting, [n for n in args.names if n != args.holdout])
        named, total = false_accepts(segs_b, spans)

        rows.append((floor, a, named, total))
        print(f"  cpCER {a['cp']:.2f}%  미상 {a['missed']}  오배정 {a['wrong']}  "
              f"| 명단 밖 오수락 {named}/{total}")

    # B조건(홀드아웃 제외)이 매 floor의 마지막 refine_with라서, 루프가 끝나면
    # profiles.npz가 홀드아웃 제외 상태로 남는다 — 복원 안 하면 이후 이 회의로
    # 뭘 재든 홀드아웃 인물이 영구히 명단 밖 취급된다(2026-09-08 실측 오류로 발견:
    # 이 복원이 없어서 8b5f84b7/ded1105f/ba8f38c4 전부 다음날 오염된 프로필로
    # 시험이 진행됐었다). 전원 후보로 되돌려놓는다.
    if rows:
        print("\n정리: profiles.npz를 전원 후보로 복원 중...")
        refine_with(args.meeting, args.names)

    print(f"\n{'=' * 78}")
    print(f"{'하한':>6s}{'cpCER':>9s}{'화자대가':>9s}{'미상':>6s}{'오배정':>7s}{'명단밖 오수락':>14s}")
    print("-" * 78)
    for floor, a, named, total in rows:
        print(f"{floor:>6s}{a['cp']:8.2f}%{a['cost']:8.2f}%{a['missed']:6d}{a['wrong']:7d}"
              f"{f'{named}/{total}':>14s}")
    print()
    print("읽는 법")
    print("  A(왼쪽 4열): 하한을 낮출수록 미상이 줄고 cpCER이 내려가는 게 기대되는 이득")
    print("  B(오수락)  : **0이어야 안전하다.** 늘기 시작하는 지점 앞에서 멈출 것")
    print("               — 명단 밖 사람의 발언에 남의 이름이 붙는 것은 미상보다 나쁘다")
    print()
    print("  ⚠️ 회의 한 건 결과다. 방향이 잡히면 나머지 회의로 확인할 것.")
    print("  ⚠️ 끝나면 서버가 마지막 하한으로 떠 있다 — 채택 값으로 다시 띄울 것.")


if __name__ == "__main__":
    main()
