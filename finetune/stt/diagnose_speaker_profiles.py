"""
화자 오배정 원인 진단 — 목소리 지문이 실제로 얼마나 갈리는지 숫자로 확인한다.

왜 필요한가:
  "누가 말했는지 틀렸다"는 관찰만으로는 원인을 못 좁힌다. 지문이 겹치는 건지,
  임계값이 문제인지, 특정 프로필만 나쁜 건지 구분해야 대응이 달라진다.
  추측으로 임계값을 만지면 다른 화자가 깨진다.

두 가지를 잰다:
  1. 프로필 간 유사도 — 등록된 목소리끼리 얼마나 구분되는가.
     서로 0.5(SPEAKER_SIMILARITY_THRESHOLD) 이상이면 애초에 구분이 어렵다.
  2. 특정 구간의 실제 유사도 — 그 구간 음성이 각 프로필과 얼마나 닮았는지 전부 출력.
     1등과 2등의 격차가 좁으면 판정이 흔들리는 구간이다.

사용법:
  python diagnose_speaker_profiles.py
  python diagnose_speaker_profiles.py --meeting <회의ID> --at 94.4-103.8 139.0-148.6
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, REALTIME_SAMPLE_RATE, SPEAKER_SIMILARITY_THRESHOLD,
)
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--speakers", nargs="*", default=None)
    parser.add_argument("--meeting", default=None, help="구간 진단에 쓸 회의 ID")
    parser.add_argument("--at", nargs="*", default=[],
                        help="진단할 구간 '시작-끝'(초). 예: 94.4-103.8")
    parser.add_argument("--audio", default="audio.wav")
    args = parser.parse_args()

    store = GlobalProfileStore()
    names = args.speakers or store.list_names()
    profiles = store.load(names)
    if len(profiles) < 2:
        raise SystemExit("❌ 비교하려면 프로필이 2개 이상 필요")

    labels = list(profiles)
    width = max(len(n) for n in labels) + 2

    # ── 1. 프로필 간 유사도 ────────────────────────────────
    print("=" * 60)
    print("프로필 간 유사도 — 등록된 목소리끼리 구분이 되는가")
    print("=" * 60)
    print(" " * width + "".join(f"{n:>10s}" for n in labels))
    worst = []
    for a in labels:
        row = f"{a:<{width}s}"
        for b in labels:
            s = 1.0 if a == b else cosine(profiles[a], profiles[b])
            row += f"{s:>10.3f}"
            if a < b:
                worst.append((s, a, b))
        print(row)

    worst.sort(reverse=True)
    print(f"\n임계값 {SPEAKER_SIMILARITY_THRESHOLD} — 이보다 높으면 같은 사람으로 본다")
    print("가장 헷갈리는 조합:")
    for s, a, b in worst[:3]:
        flag = "⚠️ 임계값 초과 — 구분 불가" if s >= SPEAKER_SIMILARITY_THRESHOLD else "정상 범위"
        print(f"  {a} ↔ {b}: {s:.3f}   {flag}")

    if not args.meeting or not args.at:
        return

    # ── 2. 특정 구간이 각 프로필과 얼마나 닮았는지 ──────────
    path = os.path.join(MEETINGS_DIR, args.meeting, args.audio)
    if not os.path.isfile(path):
        raise SystemExit(f"❌ 오디오 없음: {path}")
    audio, sample_rate = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference(), initial_profiles=profiles)

    print("\n" + "=" * 60)
    print("구간별 실제 유사도 — 1등과 2등의 격차가 좁으면 판정이 흔들린다")
    print("=" * 60)
    for spec in args.at:
        start, end = (float(x) for x in spec.split("-"))
        clip = audio[int(start * sample_rate):int(end * sample_rate)]
        if len(clip) == 0:
            print(f"\n[{spec}] 구간이 비어 있음")
            continue
        # identify()와 동일한 전처리(가장 긴 발화 구간만 사용)를 거쳐야 같은 조건이 된다
        region = identifier._dominant_speech_region(clip)
        embedding = identifier.extract_embedding(region)

        scores = sorted(
            ((cosine(embedding, profiles[n]), n) for n in labels), reverse=True
        )
        print(f"\n[{start:.1f}s ~ {end:.1f}s]  ({len(region)/REALTIME_SAMPLE_RATE:.1f}초 사용)")
        for rank, (s, n) in enumerate(scores, 1):
            mark = " ← 판정" if rank == 1 else ""
            print(f"   {rank}. {n:<10s} {s:.3f}{mark}")
        gap = scores[0][0] - scores[1][0]
        verdict = "✅ 뚜렷" if gap >= 0.10 else ("⚠️ 애매" if gap >= 0.05 else "❌ 사실상 구분 안 됨")
        print(f"   1·2등 격차 {gap:.3f}  {verdict}")


if __name__ == "__main__":
    main()
