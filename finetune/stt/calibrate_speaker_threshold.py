"""
화자 판정 문턱을 **발화 길이의 함수로** 보정한다.

왜 필요한가 (2026-08-13):
  절대 하한을 상수 하나로 두고 0.4 → 0.35 → 0.30 → 0.25로 계속 조정해왔지만
  매번 한 회의에서 좋아지고 다른 회의에서 나빠졌다. 오늘 창 길이를 바꿔가며 재보니
  이유가 드러났다 — **같은 오수락률을 주는 문턱이 길이마다 다르다:**

      창 1.5초 → 0.500 (등록자 24% 통과)
      창 2.5초 → 0.525 (38%)
      창 4.0초 → 0.575 (42%)

  오디오가 길수록 임베딩이 안정돼 점수가 올라간다. **상수 하나로 정할 수 있는 값이
  애초에 아니었다.** 짧은 발화에 맞추면 긴 발화를 낭비하고, 긴 발화에 맞추면 짧은
  발화를 전부 버린다. 지금까지 그 사이를 오간 것이다.

  길이의 함수로 두면 **앞으로 어떤 길이가 들어와도 그 길이에 맞는 기준**이 적용된다.

⚠️ 우리 회의 4건(사람 5명)으로 곡선을 뽑으면 또 그 5명에 맞춰진다. 그래서 두 출처를
   함께 쓴다:

     AI-Hub  화자 수백 명 — 곡선의 **모양**을 여기서 정한다(과적합 없음)
     우리 회의 — 그 곡선이 우리 녹음 조건에서도 성립하는지 **확인만** 한다

   조건(마이크·방·등록 방식)이 다르므로 AI-Hub 값을 그대로 쓰면 안 되고,
   **두 출처에서 곡선의 기울기가 같은 방향인지**를 보는 것이 목적이다.

사용법:
  python calibrate_speaker_threshold.py --meetings <회의ID>:<대본> ...
  python calibrate_speaker_threshold.py --manifest manifest_aihub_25k.jsonl \\
      --roster 5 --enroll 3 --speakers 60
"""
import argparse
import io
import json
import os
import random
import sys
import zipfile

import numpy as np
import soundfile as sf

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR, REALTIME_SAMPLE_RATE  # noqa: E402
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)
from probe_score_norm import cosine, truth_spans  # noqa: E402

# 길이 구간. 짧은 쪽을 촘촘히 나눈다 — 문제가 거기서 생기고, 길어질수록 차이가 준다.
BUCKETS = [(0.8, 1.5), (1.5, 2.5), (2.5, 4.0), (4.0, 8.0), (8.0, 1e9)]


def bucket_of(sec: float):
    for lo, hi in BUCKETS:
        if lo <= sec < hi:
            return (lo, hi)
    return None


def read_audio(item: dict) -> tuple[np.ndarray, int] | None:
    """AI-Hub 매니페스트는 wav 경로일 수도, zip 내부 위치일 수도 있다."""
    path = item.get("audio")
    if path and os.path.isfile(path):
        a, sr = sf.read(path, dtype="float32")
    elif item.get("audio_zip") and item.get("audio_member"):
        try:
            with zipfile.ZipFile(item["audio_zip"]) as z:
                a, sr = sf.read(io.BytesIO(z.read(item["audio_member"])), dtype="float32")
        except Exception:
            return None
    else:
        return None
    if a.ndim > 1:
        a = a.mean(axis=1)
    return a, sr


def trials_from_meetings(specs, profiles, identifier):
    """우리 회의: 대본 정렬로 얻은 발화 구간을 **통째로** 한 시행으로 쓴다."""
    names_all = sorted(profiles)
    inn, out = [], []
    for spec in specs:
        meeting, script = spec.split(":", 1)
        audio, sr = sf.read(os.path.join(MEETINGS_DIR, meeting, "audio.wav"), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        for speaker, start, end in truth_spans(meeting, os.path.join(_HERE, script)):
            if speaker not in profiles or end - start < BUCKETS[0][0]:
                continue
            emb = identifier.extract_embedding(audio[int(start * sr):int(end * sr)])
            others = [n for n in names_all if n != speaker]
            if len(others) < 3:
                continue
            # 후보 수를 양쪽 4명으로 맞춘다(점수 분포가 후보 수에 따라 달라지므로)
            cand_in = [n for n in names_all if n != others[0]]
            top_in = max((cosine(emb, profiles[n]), n) for n in cand_in)
            inn.append((top_in[1] == speaker, top_in[0], end - start))
            top_out = max(cosine(emb, profiles[n]) for n in others)
            out.append((False, top_out, end - start))
    return inn, out


def trials_from_manifest(path, identifier, roster: int, enroll: int, speakers: int, seed: int):
    """AI-Hub: 화자별로 몇 개는 등록용, 나머지는 시험용으로 쓴다.

    명단(roster) 안 화자의 발화는 등록자 시행, **명단 밖 화자의 발화는 그대로
    명단 밖 시행**이 된다 — 우리 회의처럼 억지로 빼낼 필요가 없다.
    """
    by_spk = {}
    for line in open(path, encoding="utf-8"):
        d = json.loads(line)
        by_spk.setdefault(d.get("speaker", "?"), []).append(d)
    usable = {k: v for k, v in by_spk.items() if len(v) >= enroll + 2}
    rng = random.Random(seed)
    chosen = rng.sample(sorted(usable), min(speakers, len(usable)))
    print(f"  화자 {len(usable)}명 중 {len(chosen)}명 사용 (명단 {roster}명씩)")

    inn, out = [], []
    for i in range(0, len(chosen) - roster, roster):
        group = chosen[i:i + roster]
        profiles, tests = {}, []
        for spk in group:
            items = usable[spk]
            embs = []
            for it in items[:enroll]:
                got = read_audio(it)
                if got is None:
                    continue
                a, sr = got
                if len(a) >= sr:
                    embs.append(identifier.extract_embedding(a))
            if not embs:
                continue
            profiles[spk] = np.mean(embs, axis=0)
            tests += [(spk, it) for it in items[enroll:enroll + 3]]
        if len(profiles) < 3:
            continue
        # 명단 밖 화자 — 이 그룹에 없는 사람들에서 뽑는다
        outsiders = [s for s in chosen if s not in profiles][:roster]
        for spk in outsiders:
            tests += [(None, it) for it in usable[spk][enroll:enroll + 2]]

        for true_spk, it in tests:
            got = read_audio(it)
            if got is None:
                continue
            a, sr = got
            dur = len(a) / sr
            if dur < BUCKETS[0][0]:
                continue
            emb = identifier.extract_embedding(a)
            score, name = max((cosine(emb, v), k) for k, v in profiles.items())
            if true_spk is None:
                out.append((False, score, dur))
            else:
                inn.append((name == true_spk, score, dur))
    return inn, out


def calibrate(inn, out, far_limit: float):
    """길이 구간마다 '오수락 한도를 지키면서 가장 많이 건지는' 문턱을 찾는다."""
    rows = []
    for lo, hi in BUCKETS:
        k = [(ok, s) for ok, s, d in inn if lo <= d < hi]
        u = [s for _ok, s, d in out if lo <= d < hi]
        if len(k) < 10 or len(u) < 10:
            rows.append((lo, hi, len(k), len(u), None, 0.0, 0.0, 0.0))
            continue
        best = None
        for g in np.arange(0.20, 0.80, 0.0125):
            passed = [ok for ok, s in k if s >= g]
            far = sum(1 for s in u if s >= g) / len(u)
            if far > far_limit or not passed:
                continue
            gain = len(passed) / len(k) * (sum(passed) / len(passed))
            if best is None or gain > best[3]:
                best = (g, len(passed) / len(k), sum(passed) / len(passed), gain, far)
        if best is None:
            rows.append((lo, hi, len(k), len(u), None, 0.0, 0.0, 0.0))
        else:
            rows.append((lo, hi, len(k), len(u), best[0], best[1], best[2], best[4]))
    return rows


def show(title, rows):
    print(f"\n{title}")
    print(f"  {'길이(초)':>12s}{'등록자':>7s}{'명단밖':>7s}{'문턱':>8s}{'통과율':>8s}{'정확도':>8s}{'오수락':>8s}")
    for lo, hi, nk, nu, g, cov, acc, far in rows:
        span = f"{lo:.1f}~{'∞' if hi > 1e8 else f'{hi:.1f}'}"
        if g is None:
            print(f"  {span:>12s}{nk:7d}{nu:7d}{'—':>8s}{'(표본 부족 또는 조건 불만족)':>20s}")
        else:
            print(f"  {span:>12s}{nk:7d}{nu:7d}{g:8.3f}{cov:8.0%}{acc:8.0%}{far:8.1%}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="*", default=[], help="'회의ID:대본경로'")
    parser.add_argument("--manifest", default=None, help="AI-Hub jsonl")
    parser.add_argument("--roster", type=int, default=5, help="한 '회의'의 등록 인원")
    parser.add_argument("--enroll", type=int, default=3, help="등록에 쓸 발화 수")
    parser.add_argument("--speakers", type=int, default=60, help="AI-Hub에서 쓸 화자 수")
    parser.add_argument("--far", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference())

    if args.manifest:
        print(f"[AI-Hub] {args.manifest}")
        inn, out = trials_from_manifest(args.manifest, identifier, args.roster,
                                        args.enroll, args.speakers, args.seed)
        print(f"  등록자 시행 {len(inn)} / 명단 밖 시행 {len(out)}")
        show("AI-Hub — 길이별 문턱 (곡선의 모양을 여기서 본다)",
             calibrate(inn, out, args.far))

    if args.meetings:
        store = GlobalProfileStore()
        profiles = store.load(store.list_names())
        print(f"\n[우리 회의] 등록 {len(profiles)}명")
        inn, out = trials_from_meetings(args.meetings, profiles, identifier)
        print(f"  등록자 시행 {len(inn)} / 명단 밖 시행 {len(out)}")
        show("우리 회의 — 같은 방향인지 확인만 (값을 그대로 쓰지 말 것)",
             calibrate(inn, out, args.far))

    print("\n읽는 법")
    print("  길이가 길어질수록 문턱이 **올라가면** 가설대로다 — 긴 발화는 점수가 높게")
    print("  나오므로 더 엄격해도 되고, 짧은 발화는 낮춰야 건진다.")
    print("  두 출처에서 방향이 같으면 그 모양을 규칙으로 삼는다.")
    print("  ⚠️ 값은 AI-Hub 것을 그대로 쓰지 말 것 — 녹음 조건이 다르다.")
    print("     우리 회의 쪽 값을 쓰되, **모양(기울기)이 AI-Hub와 일치할 때만** 신뢰한다.")


if __name__ == "__main__":
    main()
