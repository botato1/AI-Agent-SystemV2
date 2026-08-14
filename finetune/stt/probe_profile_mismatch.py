"""
화자 판정이 실패하는 원인이 **사람인지 조건인지** 가른다.

왜 필요한가 (2026-08-13):
  같은 사람인데 발화마다 유사도가 0.275~0.408로 흔들리고, 사람마다 평균이
  0.30~0.53으로 갈린다. 지금까지 이 숫자를 "그 사람 프로필 품질"로 해석하고
  문턱을 조정해왔지만, 네 회의로 재보니 어떤 문턱도 통하지 않았다.

  다른 가설이 있다. **등록할 때와 회의할 때의 조건이 다르다.** 목소리 등록은
  조용한 곳에서 마이크 가까이 하고 하고, 회의는 공용 마이크에 거리도 제각각이다.
  임베딩이 그 차이를 그대로 반영한다면, 문턱을 어떻게 만져도 못 고친다 —
  비교 대상 자체가 어긋나 있는 것이기 때문이다.

무엇을 재나:
  발화 하나마다 세 가지 유사도를 낸다.

    등록 프로필      회의 전에 등록해둔 목소리와의 유사도 (지금 쓰는 값)
    회의 내 자기     같은 회의에서 그 사람의 **다른 발화들**의 평균과의 유사도
                    (자기 자신은 빼고 계산 — leave-one-out)
    회의 내 타인     같은 회의 다른 사람들의 평균 중 가장 높은 값

  **회의 내 자기 >> 등록 프로필**이면 원인은 사람이 아니라 조건이다.
  그러면 해법은 문턱이 아니라 **회의 초반에 확실히 판정된 발화로 그 회의용 프로필을
  다시 만드는 것**이 된다(화자 인식에서 쓰는 표준 적응 기법). 사람이 다시 녹음하는
  게 아니라 시스템이 자동으로 한다.

  마지막으로 **판정 정확도를 두 조건에서 비교**한다 — 등록 프로필로 순위를 매겼을 때와
  회의 내 프로필로 매겼을 때. 후자가 뚜렷이 높으면 적응이 실제로 통한다는 뜻이다.

사용법:
  python probe_profile_mismatch.py --meetings <회의ID>:<대본> ...
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR  # noqa: E402
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)
from probe_score_norm import cosine, truth_spans  # noqa: E402

MIN_SPAN_SEC = 1.0


def collect(meeting: str, script: str, identifier):
    """발화 구간마다 임베딩을 뽑고 (화자, 임베딩, 길이)로 모은다."""
    audio, sr = sf.read(os.path.join(MEETINGS_DIR, meeting, "audio.wav"), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    out = []
    for speaker, start, end in truth_spans(meeting, script):
        if end - start < MIN_SPAN_SEC:
            continue
        out.append((speaker, identifier.extract_embedding(audio[int(start * sr):int(end * sr)]),
                    end - start))
    return out


def centroid(embs):
    return np.mean(embs, axis=0) if embs else None


def analyse(rows, profiles):
    """화자별 통계 + 두 조건의 판정 정확도."""
    by_spk: dict[str, list] = {}
    for spk, emb, dur in rows:
        by_spk.setdefault(spk, []).append(emb)

    # 회의 내 프로필(전체 평균) — 타인 비교용
    meeting_centroid = {s: centroid(e) for s, e in by_spk.items() if len(e) >= 2}

    per_speaker, hit_enrolled, hit_adapted, total = [], 0, 0, 0
    for spk, embs in by_spk.items():
        if len(embs) < 2 or spk not in profiles:
            continue
        sims_enr, sims_self, sims_other = [], [], []
        for i, emb in enumerate(embs):
            sims_enr.append(cosine(emb, profiles[spk]))
            # 자기 자신은 빼고 나머지로 중심을 만든다 — 안 그러면 자기와 비교하게 된다
            loo = centroid([e for j, e in enumerate(embs) if j != i])
            sims_self.append(cosine(emb, loo))
            others = [cosine(emb, c) for s, c in meeting_centroid.items() if s != spk]
            sims_other.append(max(others) if others else 0.0)

            # 판정 정확도 — 등록 프로필 기준
            ranked_enr = max((cosine(emb, v), k) for k, v in profiles.items())
            hit_enrolled += (ranked_enr[1] == spk)
            # 판정 정확도 — 회의 내 프로필 기준(자기 것은 leave-one-out으로 교체)
            cands = {s: (loo if s == spk else c) for s, c in meeting_centroid.items()}
            ranked_ad = max((cosine(emb, v), k) for k, v in cands.items())
            hit_adapted += (ranked_ad[1] == spk)
            total += 1

        per_speaker.append((spk, len(embs), float(np.mean(sims_enr)),
                            float(np.mean(sims_self)), float(np.mean(sims_other))))
    return per_speaker, hit_enrolled, hit_adapted, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True, help="'회의ID:대본경로'")
    args = parser.parse_args()

    store = GlobalProfileStore()
    profiles = store.load(store.list_names())
    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference())
    print(f"등록 프로필 {len(profiles)}명\n")

    g_enr = g_ad = g_tot = 0
    for spec in args.meetings:
        meeting, script = spec.split(":", 1)
        rows = collect(meeting, os.path.join(_HERE, script), identifier)
        per, he, ha, tot = analyse(rows, profiles)
        if not tot:
            print(f"{meeting[:38]} — 표본 부족, 건너뜀"); continue
        g_enr += he; g_ad += ha; g_tot += tot

        print(f"[{meeting[:38]}]")
        print(f"  {'화자':8s}{'발화':>5s}{'등록프로필':>11s}{'회의내 자기':>12s}{'회의내 타인':>12s}{'차이':>8s}")
        for spk, n, enr, self_, other in sorted(per, key=lambda r: r[2]):
            print(f"  {spk:8s}{n:5d}{enr:11.3f}{self_:12.3f}{other:12.3f}{self_ - enr:+8.3f}")
        print(f"  판정 정확도 — 등록 프로필 {he}/{tot} ({he/tot:.0%})"
              f"  /  회의 내 프로필 {ha}/{tot} ({ha/tot:.0%})\n")

    if g_tot:
        print("=" * 70)
        print(f"전체 {g_tot}발화 — 등록 프로필 {g_enr/g_tot:.0%}  /  회의 내 프로필 {g_ad/g_tot:.0%}")
        print("=" * 70)
    print("""
읽는 법
  '회의내 자기'가 '등록프로필'보다 크게 높으면 → 원인은 사람이 아니라 **조건 차이**다.
     등록 음성과 회의 음성의 마이크·거리·방이 다른 것이므로, 문턱으로는 못 고친다.
     해법: 회의 초반에 확실히 판정된 발화로 그 회의용 프로필을 만들어 나머지를 판정.

  '회의내 자기'가 '회의내 타인'보다 충분히 높아야 적응이 의미 있다.
     둘이 비슷하면 회의 안에서도 사람을 구분 못 한다는 뜻이라 다른 접근이 필요하다.

  판정 정확도 두 값의 차이가 곧 **적응으로 얻을 수 있는 상한**이다.
  ⚠️ 회의 내 프로필은 정답을 알고 만든 것이라 실제보다 유리하다. 실제로는 초반
     발화를 스스로 판정해서 만들어야 하므로 이 값보다 낮게 나온다.""")


if __name__ == "__main__":
    main()
