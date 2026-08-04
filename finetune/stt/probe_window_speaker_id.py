"""
"짧은 창으로 화자를 직접 판정할 수 있는가"를 재는 실험.

배경:
  지금 재분석은 pyannote 클러스터링 결과에 이름을 붙이는 방식이라, 클러스터링이
  틀리면 같이 틀린다. 실측(5인 공용 마이크 회의)에서 pyannote가 이준오·이승주를
  한 클러스터로 묶어 15.9초를 모아도 최고 유사도가 0.37(엉뚱한 사람)이었다.

  그런데 우리는 **참석자가 누구인지, 목소리가 어떤지 이미 알고 있다.** 클러스터링에
  기대지 말고 짧은 창마다 등록 프로필과 직접 대조하면 클러스터링 실패에 종속되지 않는다.

  이 스크립트는 그 방식이 성립하는지만 확인한다 — 창이 짧으면 임베딩이 흔들려서
  판정이 안 될 수 있고, 그러면 방향 자체가 무의미하다. **만들기 전에 잰다.**

같이 확인하는 것:
  음량 정규화(창마다 RMS를 맞춤)가 도움이 되는지. 실패한 두 사람이 마이크에서 멀어
  작게 녹음됐기 때문에(RMS 0.046 / 0.056 vs 성공한 사람들 0.073~0.100),
  낮은 SNR이 임베딩을 흐렸을 가능성이 있다.

사용법:
  python probe_window_speaker_id.py --meeting <회의ID> \
      --truth 이준오:41.3-50.5 이승주:52.6-60.5 김나연:61.1-70.0 문지수:24-40 가동현:88.6-98
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR, REALTIME_SAMPLE_RATE  # noqa: E402
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)


def cosine(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def normalize_rms(clip: np.ndarray, target: float = 0.08) -> np.ndarray:
    """창마다 음량을 맞춘다. 멀리서 녹음된 화자의 낮은 SNR을 보정하려는 시도."""
    rms = np.sqrt((clip ** 2).mean())
    if rms < 1e-6:
        return clip
    return np.clip(clip * (target / rms), -1.0, 1.0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--truth", nargs="+", required=True,
                        help="정답 구간 '이름:시작-끝' (초)")
    parser.add_argument("--window", type=float, default=1.5, help="창 길이(초)")
    parser.add_argument("--hop", type=float, default=0.5, help="창 이동(초)")
    args = parser.parse_args()

    path = os.path.join(MEETINGS_DIR, args.meeting, args.audio)
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    store = GlobalProfileStore()
    profiles = store.load(store.list_names())
    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference())

    win = int(args.window * sr)
    hop = int(args.hop * sr)

    print(f"창 {args.window}초 / 이동 {args.hop}초 / 등록 {len(profiles)}명\n")
    print(f"{'정답':8s}{'창수':>5s}{'정답1등':>8s}{'정규화시':>9s}"
          f"{'평균유사도':>11s}{'정규화시':>9s}   오답으로 뽑힌 이름")
    print("-" * 78)

    totals = {"plain_hit": 0, "norm_hit": 0, "count": 0}
    for spec in args.truth:
        name, span = spec.split(":")
        start, end = (float(x) for x in span.split("-"))
        seg = audio[int(start * sr):int(end * sr)]

        hits = norm_hits = 0
        scores, norm_scores = [], []
        wrong: dict = {}
        n = 0
        for off in range(0, max(len(seg) - win + 1, 1), hop):
            clip = seg[off:off + win]
            if len(clip) < win // 2:
                break
            n += 1
            for tag, c in (("plain", clip), ("norm", normalize_rms(clip))):
                emb = identifier.extract_embedding(c)
                ranked = sorted(((cosine(emb, v), k) for k, v in profiles.items()), reverse=True)
                top_score, top_name = ranked[0]
                if tag == "plain":
                    scores.append(top_score)
                    if top_name == name:
                        hits += 1
                    else:
                        wrong[top_name] = wrong.get(top_name, 0) + 1
                else:
                    norm_scores.append(top_score)
                    if top_name == name:
                        norm_hits += 1

        if not n:
            continue
        totals["plain_hit"] += hits
        totals["norm_hit"] += norm_hits
        totals["count"] += n
        wrong_str = ", ".join(f"{k} {v}" for k, v in sorted(wrong.items(), key=lambda x: -x[1])[:3])
        print(f"{name:8s}{n:5d}{hits/n*100:7.0f}%{norm_hits/n*100:8.0f}%"
              f"{np.mean(scores):10.3f}{np.mean(norm_scores):9.3f}   {wrong_str}")

    c = max(totals["count"], 1)
    print("-" * 78)
    print(f"{'전체':8s}{c:5d}{totals['plain_hit']/c*100:7.0f}%{totals['norm_hit']/c*100:8.0f}%")
    print()
    print("판정 기준:")
    print("  정답1등 80% 이상 → 창 단위 판정이 성립. 이 방향으로 구현할 가치 있음")
    print("  50~80%          → 창을 늘리거나 평활화(이웃 창 다수결)가 필요")
    print("  50% 미만        → 짧은 창으로는 무리. 다른 접근을 찾아야 함")


if __name__ == "__main__":
    main()
