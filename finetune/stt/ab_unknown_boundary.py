"""
SPEAKER_UNKNOWN_AS_BOUNDARY를 켜고 끈 두 조건을 여러 회의로 A/B 한다.

무엇을 묻는가 (2026-08-14):
  낮은 유사도 발화에 **이름을 붙이는** 시도는 전부 실패했다 — 절대 하한 0.30/0.25/0.15,
  점수 정규화, 회의 내 적응까지 네 회의 데이터에서 모두 기각됐다(오수락이 1/14 → 11/14로
  늘기만 했다). 그래서 방향을 바꿨다.

  **미상 구간을 화자 경계로 인정한다.** 이름을 못 붙이는 건 똑같지만, 그 발화가
  speaker=null인 자기 세그먼트를 갖게 되어 **옆 사람 이름이 잘못 붙지는 않는다.**
  문턱은 건드리지 않는다 — 0.35 그대로 두고 미상의 결과만 바꾼다.

  기대: 오배정↓ (이게 목적), 미상↑ (대가), cpCER은 개선되어야 한다.
  cpCER이 나빠지면 채택하지 않는다.

왜 이 도구가 따로 필요한가:
  sweep_speaker_floor.py는 회의 하나씩만 돌고 조건마다 서버를 다시 띄운다. 여기서는
  회의 4건 × 조건 2개라 그 방식이면 재기동만 8번이다. 조건당 한 번만 띄우고 회의를
  도는 게 같은 결과를 훨씬 빠르게 준다.

⚠️ 참가자 명단은 대본에서 읽는다. 회의마다 인원이 달라서(5인/4인) 손으로 넘기면 틀린다.
⚠️ demo_prep 회의(36256894)는 넣지 말 것 — 화자 지문을 그 회의 오디오에서 만들었다.
   자기가 만든 데이터로 자기를 채점하는 셈이라 실제보다 좋게 나온다.

사용법:
  python ab_unknown_boundary.py --meetings <회의ID>:scripts/xxx.txt ...
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from evaluate_against_script import load_script  # noqa: E402
from sweep_speaker_floor import restart, refine_with, score  # noqa: E402

CONDITIONS = [("끔(현행)", "0"), ("켬", "1")]


def names_from_script(path: str) -> list[str]:
    """대본에 실제로 등장하는 화자만 후보로 쓴다."""
    seen, out = set(), []
    for line in load_script(path):
        if line["speaker"] not in seen:
            seen.add(line["speaker"]); out.append(line["speaker"])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True, help="'회의ID:대본경로'")
    parser.add_argument("--floor", default="0.35", help="절대 하한. 이 시험에서는 고정한다")
    args = parser.parse_args()

    pairs = []
    for spec in args.meetings:
        meeting, script = spec.split(":", 1)
        names = names_from_script(os.path.join(_HERE, script))
        pairs.append((meeting, script, names))
        print(f"{meeting[:38]}  참석 {len(names)}명: {' '.join(names)}")

    results: dict[str, dict[str, dict]] = {}
    for label, value in CONDITIONS:
        print(f"\n{'=' * 70}\nUNKNOWN_AS_BOUNDARY {label}\n{'=' * 70}")
        if not restart(args.floor, f"SPEAKER_UNKNOWN_AS_BOUNDARY={value}"):
            sys.exit("❌ 서버가 안 뜬다 — 중단")
        results[value] = {}
        for meeting, script, names in pairs:
            refine_with(meeting, names)
            s = score(meeting, script)
            if not s:
                print(f"  ⚠️ {meeting[:38]} 채점 실패"); continue
            results[value][meeting] = s
            print(f"  {meeting[:38]}  cpCER {s['cp']:6.2f}%  "
                  f"미상 {s['missed']:2d}  오배정 {s['wrong']:2d}")

    print(f"\n{'=' * 86}")
    print(f"{'회의':<40s}{'cpCER 끔':>10s}{'cpCER 켬':>10s}{'Δ':>8s}"
          f"{'오배정':>10s}{'미상':>8s}")
    print("-" * 86)
    tot = {"0": [], "1": []}
    for meeting, _, _ in pairs:
        a, b = results.get("0", {}).get(meeting), results.get("1", {}).get(meeting)
        if not (a and b):
            continue
        tot["0"].append(a); tot["1"].append(b)
        wrong = f"{a['wrong']}→{b['wrong']}"
        missed = f"{a['missed']}→{b['missed']}"
        print(f"{meeting[:38]:<40s}{a['cp']:9.2f}%{b['cp']:9.2f}%{b['cp'] - a['cp']:+8.2f}"
              f"{wrong:>10s}{missed:>8s}")
    if tot["0"]:
        n = len(tot["0"])
        ma = sum(r["cp"] for r in tot["0"]) / n
        mb = sum(r["cp"] for r in tot["1"]) / n
        wa = sum(r["wrong"] for r in tot["0"]); wb = sum(r["wrong"] for r in tot["1"])
        ua = sum(r["missed"] for r in tot["0"]); ub = sum(r["missed"] for r in tot["1"])
        print("-" * 86)
        wrong = f"{wa}→{wb}"
        missed = f"{ua}→{ub}"
        print(f"{'평균 / 합계':<40s}{ma:9.2f}%{mb:9.2f}%{mb - ma:+8.2f}"
              f"{wrong:>10s}{missed:>8s}")
    print(f"""
읽는 법
  목적은 **오배정을 줄이는 것**이다. 오배정이 줄고 cpCER이 나빠지지 않으면 채택.
  미상이 느는 건 예상된 대가다 — 틀린 이름보다 낫다.
  cpCER이 오르면(나빠지면) 채택하지 않는다. 회의별로 방향이 엇갈려도 채택하지 않는다.

  ⚠️ 끝나면 서버가 마지막 조건으로 떠 있다. 결론대로 다시 띄울 것.""")


if __name__ == "__main__":
    main()
