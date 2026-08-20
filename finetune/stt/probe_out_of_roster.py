"""
"참석자 명단에 없는 사람이 말하면 어떻게 되는가"를 재고, 막을 문턱을 찾는다.

문제:
  참석자를 아는 회의는 순위로 판정한다("다섯 중 누가 제일 닮았나"). 이 방식은
  **무조건 누군가를 지목한다.** 명단에 없는 사람이 말해도 제일 비슷한 참석자
  이름이 붙는다는 뜻이다.

  실측(2026-08-04): 5인 회의를 3명 프로필로 돌렸더니 이준오·이승주의 발화가
  가동현·문지수로 밀려들어갔다. 회의 끝난 뒤 잡음에 "이승주"가 붙기도 했다.
  margin은 이걸 못 막는다 — 명단 안에서 1등과 2등이 갈리기만 하면 통과하므로,
  명단 밖 목소리가 특정 참석자 쪽으로 치우쳐 있으면 margin이 오히려 크게 나온다.

  그래서 **절대 유사도 바닥**이 하나 필요하다: 순위 1등이라도 이 정도조차 안
  닮았으면 미상으로 둔다. 순위 판정을 되돌리는 게 아니라, 명단 밖만 걸러내는
  최소한의 방어선이다. 절대 문턱(0.4)이 정답까지 걷어냈던 것과 달리, 바닥은
  훨씬 낮게 잡아야 한다 — 얼마나 낮게 잡을지가 이 스크립트로 재는 값이다.

재는 방법:
  --exclude로 몇 명을 명단에서 빼고, 그 사람들의 발화 구간(= 명단 밖)과
  남은 사람들의 발화 구간(= 명단 안)에서 각각 1등 유사도 분포를 뽑는다.
  둘이 갈리는 지점이 바닥값 후보다.

사용법:
  python probe_out_of_roster.py --meeting <회의ID> --exclude 이준오 이승주 \
      --truth 이준오:41.3-50.5 이승주:52.6-60.5 김나연:61.1-70.0 문지수:24-40 가동현:88.6-98
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, SPEAKER_MIN_MARGIN, SPEAKER_WINDOW_SEC, SPEAKER_WINDOW_HOP_SEC,
)
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--truth", nargs="+", required=True, help="'이름:시작-끝' (초)")
    parser.add_argument("--exclude", nargs="+", required=True,
                        help="참석자 명단에서 뺄 이름 — 이 사람들의 발화가 '명단 밖' 표본이 된다")
    args = parser.parse_args()

    audio, sr = sf.read(os.path.join(MEETINGS_DIR, args.meeting, args.audio), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    store = GlobalProfileStore()
    roster = [n for n in store.list_names() if n not in args.exclude]
    profiles = store.load(roster)
    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference(), initial_profiles=profiles)

    win, hop = int(SPEAKER_WINDOW_SEC * sr), int(SPEAKER_WINDOW_HOP_SEC * sr)
    print(f"명단 {len(roster)}명: {', '.join(roster)}")
    print(f"명단 밖: {', '.join(args.exclude)}\n")
    print(f"{'구간':10s}{'분류':10s}{'창수':>5s}{'평균유사도':>11s}{'최고':>7s}{'margin통과':>11s}   지목된 이름")
    print("-" * 78)

    inside: list[float] = []
    outside: list[float] = []

    for spec in args.truth:
        name, span = spec.split(":")
        start, end = (float(x) for x in span.split("-"))
        seg = audio[int(start * sr):int(end * sr)]
        is_out = name in args.exclude

        scores, passed, picks = [], 0, {}
        for off in range(0, max(len(seg) - win + 1, 1), hop):
            clip = seg[off:off + win]
            if len(clip) < win // 2:
                break
            ranked = identifier.rank_profiles(identifier.extract_embedding(clip))
            top_score, top_name = ranked[0]
            margin = top_score - (ranked[1][0] if len(ranked) > 1 else top_score)
            scores.append(top_score)
            if margin >= SPEAKER_MIN_MARGIN:
                passed += 1
                picks[top_name] = picks.get(top_name, 0) + 1
            (outside if is_out else inside).append(top_score)

        if not scores:
            continue
        pick_str = ", ".join(f"{k} {v}" for k, v in sorted(picks.items(), key=lambda x: -x[1])[:3])
        print(f"{name:10s}{'명단 밖' if is_out else '명단 안':10s}{len(scores):5d}"
              f"{np.mean(scores):11.3f}{max(scores):7.3f}{passed / len(scores) * 100:10.0f}%   {pick_str}")

    if not outside or not inside:
        raise SystemExit("\n❌ 명단 안/밖 표본이 둘 다 있어야 비교가 된다")

    print("-" * 78)
    print(f"명단 안 1등 유사도: 평균 {np.mean(inside):.3f}, 하위 5% {np.percentile(inside, 5):.3f}")
    print(f"명단 밖 1등 유사도: 평균 {np.mean(outside):.3f}, 상위 5% {np.percentile(outside, 95):.3f}")

    print(f"\n바닥값 후보 (이 미만이면 순위 1등이라도 미상)")
    print(f"{'바닥':>6s}{'명단 안 유지':>13s}{'명단 밖 차단':>13s}")
    for floor in (0.15, 0.20, 0.22, 0.25, 0.28, 0.30, 0.35):
        keep = sum(s >= floor for s in inside) / len(inside) * 100
        block = sum(s < floor for s in outside) / len(outside) * 100
        print(f"{floor:6.2f}{keep:12.0f}%{block:12.0f}%")

    print("\n읽는 법:")
    print("  '명단 안 유지'가 100%에 가까우면서 '명단 밖 차단'이 가장 높은 값을 고른다")
    print("  둘이 겹쳐서 못 가르면(차단률이 낮은데 유지율부터 떨어지면) 바닥값으로는")
    print("  못 막는다는 뜻이므로, 그때는 다른 방법을 찾아야 한다")


if __name__ == "__main__":
    main()
