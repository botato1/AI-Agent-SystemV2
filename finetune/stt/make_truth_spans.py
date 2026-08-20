"""
대본과 전사를 맞춰 **"이 시간대는 누가 말했다"** 정답 구간을 만든다.

왜 필요한가 (2026-08-13):
  probe_window_speaker_id.py로 창 단위 화자 판정을 재려면 정답 구간이 필요한데,
  우리 대본에는 시각 정보가 없다. 사람이 일일이 초를 적는 건 회의마다 반복해야 해서
  현실적이지 않다.

  그런데 **전사는 시각이 정확하고 텍스트도 정확하다**(실측 CER 6.20%). 대본 줄을
  전사 세그먼트에 텍스트로 정렬하면 그 세그먼트의 시각이 곧 그 대본 줄의 시각이다.
  화자는 대본에서 오므로, 전사의 (틀릴 수 있는) 화자 라벨은 쓰지 않는다.

  즉 **정확한 부분(전사 시각)만 빌리고, 못 믿을 부분(화자 라벨)은 안 쓴다.**

⚠️ 한계:
  - 문장 단위로 쪼갠 세그먼트는 시각이 추정치다(time_estimated). 경계가 수백 ms
    어긋날 수 있어 기본적으로 양끝을 0.3초씩 잘라낸다(--trim).
  - 전사가 통째로 실패한 대본 줄은 구간을 만들 수 없어 건너뛴다.
  - 겹쳐 말한 구간은 한 사람에게만 배정된다. 정답으로 쓰기엔 부정확하므로
    대본에 [겹침] 표시가 있는 줄은 제외한다.

사용법:
  python make_truth_spans.py --meeting <회의ID> --script scripts/xxx.txt
  python probe_window_speaker_id.py --meeting <회의ID> \
      --truth $(python make_truth_spans.py --meeting <회의ID> --script scripts/xxx.txt)
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR  # noqa: E402
from evaluate_against_script import load_script, align  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--trim", type=float, default=0.3,
                        help="구간 양끝을 이만큼 잘라낸다 — 경계에서 옆 사람 목소리가 섞이는 것 방지")
    parser.add_argument("--min-sec", type=float, default=0.8,
                        help="이보다 짧아진 구간은 버린다(임베딩이 불안정한 길이)")
    parser.add_argument("--verbose", action="store_true", help="사람이 읽을 표로 출력")
    args = parser.parse_args()

    path = os.path.join(MEETINGS_DIR, args.meeting, "transcript.json")
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    # **실시간 세그먼트를 쓴다.** 재분석본은 화자 턴 기준으로 다시 잘려서 대본 한 줄이
    # 여러 화자의 말과 한 세그먼트에 섞여 있을 수 있다 — 정답을 만들 재료로는 부적합하다.
    segs = meta.get("realtime_segments") or []
    if not segs:
        raise SystemExit(f"❌ {args.meeting}: realtime_segments가 없다")
    segs = sorted(segs, key=lambda s: s.get("start", 0))

    script = load_script(os.path.expanduser(args.script))
    mapping = align(script, segs)

    spans = []
    for line, idx in zip(script, mapping):
        if line["overlapped"] or not idx:
            continue
        start = segs[idx[0]]["start"] + args.trim
        end = segs[idx[-1]]["end"] - args.trim
        if end - start < args.min_sec:
            continue
        spans.append((line["speaker"], round(start, 2), round(end, 2)))

    # 같은 사람이 이어지면 합친다 — 창을 더 많이 확보할 수 있다
    merged = []
    for spk, s, e in spans:
        if merged and merged[-1][0] == spk and s - merged[-1][2] < 0.5:
            merged[-1] = (spk, merged[-1][1], e)
        else:
            merged.append((spk, s, e))

    if args.verbose:
        total = {}
        for spk, s, e in merged:
            total[spk] = total.get(spk, 0) + (e - s)
        print(f"대본 {len(script)}줄 → 정답 구간 {len(merged)}개 "
              f"(정렬 실패로 건너뜀 {len(script) - len(spans)}줄)\n")
        for spk, s, e in merged:
            print(f"  {spk:8s} {s:6.1f}~{e:6.1f}  ({e - s:4.1f}초)")
        print("\n화자별 합계:", ", ".join(f"{k} {v:.0f}초" for k, v in sorted(total.items())))
        print("\n⚠️ 이 합계가 실제 발화량과 크게 다르면 정렬이 어긋난 것이니 그대로 쓰지 말 것.")
    else:
        print(" ".join(f"{spk}:{s}-{e}" for spk, s, e in merged))


if __name__ == "__main__":
    main()
