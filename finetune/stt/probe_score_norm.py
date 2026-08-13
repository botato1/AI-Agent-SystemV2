"""
화자 판정 **기준 자체**를 비교한다 — 절대 유사도 / margin / 점수 정규화(z).

왜 필요한가 (2026-08-13):
  절대 하한(SPEAKER_ABSOLUTE_FLOOR)을 0.4 → 0.35 → 0.30 → 0.25로 계속 조정해왔는데
  매번 한 회의에서 좋아지고 다른 회의에서 나빠졌다. 오늘 네 회의로 재보니 0.25는
  cpCER이 한 회의에서 −12%p, 다른 회의에서 **+9%p**였고 명단 밖 오수락이 3/4까지 늘었다.

  **문턱값 문제가 아니라 판정 방식 문제다.** 절대 유사도는 "누가 말했나"가 아니라
  "그 사람 프로필이 얼마나 좋은가 / 녹음이 얼마나 깨끗한가"를 잰다:

      김나연(등록됨, 프로필 약함)   0.30   ← 통과시켜야 함
      명단 밖 사람                  0.30   ← 걸러야 함

  같은 숫자다. 절대값만 보면 **어떤 문턱을 골라도 한쪽은 틀린다.**

이 스크립트가 재는 것:
  세 기준을 같은 데이터에 나란히 놓고, **"명단 밖을 거부하면서 등록자를 얼마나
  통과시키는가"**를 비교한다.

    절대   top1 점수
    margin top1 − top2                        (지금 쓰는 보조 기준)
    z      (top1 − 나머지 평균) / 나머지 표준편차   ← 화자 인식 분야의 표준(점수 정규화)

  z가 두 경우를 가르는 이유: 등록된 사람이면 **자기 프로필 하나만 튄다**(나머지는 낮음).
  모르는 사람이면 아무하고도 특별히 안 닮아 **전부 고만고만하다**. 절대값이 같아도
  이 모양이 다르다. 녹음이 나빠 점수가 전부 내려가도 평균이 같이 내려가므로 z는 버틴다.

공정한 비교를 위한 설계:
  후보 수가 다르면 점수 분포가 달라지므로 **양쪽 다 후보 4명으로 맞춘다.**
    등록자 시행    : 정답 화자를 포함하되 다른 한 명을 뺀다
    명단 밖 시행   : **정답 화자를 뺀다** — 그 창은 이제 '모르는 사람'이 말한 것이 된다
  창 하나가 두 시행에 모두 쓰이므로 표본이 자연스럽게 두 배가 되고,
  holdout을 누구로 할지 고를 필요가 없다(모든 화자가 한 번씩 명단 밖이 된다).

사용법:
  python probe_score_norm.py --meetings <회의ID>:<대본> [<회의ID>:<대본> ...]
"""
import argparse
import json
import os
import sys

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
from evaluate_against_script import load_script, align  # noqa: E402

WINDOW_SEC, HOP_SEC = 1.5, 0.5


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def truth_spans(meeting: str, script_path: str):
    """대본+실시간 전사 정렬로 (화자, 시작, 끝) 구간을 얻는다."""
    with open(os.path.join(MEETINGS_DIR, meeting, "transcript.json"), encoding="utf-8") as f:
        segs = sorted((json.load(f).get("realtime_segments") or []),
                      key=lambda s: s.get("start", 0))
    script = load_script(os.path.expanduser(script_path))
    out = []
    for line, idx in zip(script, align(script, segs)):
        if line["overlapped"] or not idx:
            continue
        start, end = segs[idx[0]]["start"] + 0.3, segs[idx[-1]]["end"] - 0.3
        if end - start >= 1.0:
            out.append((line["speaker"], start, end))
    return out


def scores_for(emb, profiles: dict, names: list[str]):
    """후보를 names로 한정해 (1등 이름, 절대, margin, z)를 낸다."""
    ranked = sorted(((cosine(emb, profiles[n]), n) for n in names), reverse=True)
    top, top_name = ranked[0]
    rest = [s for s, _ in ranked[1:]]
    margin = top - rest[0] if rest else 0.0
    # 표준편차가 0에 가까우면(후보가 하나거나 전부 동일) z가 폭발하므로 방어
    z = (top - float(np.mean(rest))) / (float(np.std(rest)) + 1e-6) if len(rest) >= 2 else 0.0
    return top_name, top, margin, z


def collect(meeting: str, script: str, profiles: dict, inference):
    """창마다 등록자 시행과 명단 밖 시행을 함께 만든다."""
    audio, sr = sf.read(os.path.join(MEETINGS_DIR, meeting, "audio.wav"), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    identifier = LiveSpeakerIdentifier(inference)
    win, hop = int(WINDOW_SEC * sr), int(HOP_SEC * sr)
    names_all = sorted(profiles)

    known, unknown = [], []
    for speaker, start, end in truth_spans(meeting, script):
        if speaker not in profiles:
            continue
        seg = audio[int(start * sr):int(end * sr)]
        for off in range(0, max(len(seg) - win + 1, 1), hop):
            clip = seg[off:off + win]
            if len(clip) < win // 2:
                break
            emb = identifier.extract_embedding(clip)
            others = [n for n in names_all if n != speaker]
            if len(others) < 3:
                continue
            # 등록자 시행: 정답을 남기고 **다른 한 명**을 빼 후보 4명
            drop = others[0]
            got, top, margin, z = scores_for(emb, profiles, [n for n in names_all if n != drop])
            known.append((got == speaker, top, margin, z))
            # 명단 밖 시행: **정답 화자**를 빼 후보 4명 — 이 창은 '모르는 사람'이 된다
            _got, top2, margin2, z2 = scores_for(emb, profiles, others)
            unknown.append((False, top2, margin2, z2))
    return known, unknown


def sweep(known, unknown, index: int, gates):
    """(문턱, 등록자 통과율, 통과분 정확도, 명단 밖 오수락률)."""
    rows = []
    for g in gates:
        k_pass = [ok for ok, *v in known if v[index - 1] >= g]
        u_pass = [1 for _ok, *v in unknown if v[index - 1] >= g]
        rows.append((
            g,
            len(k_pass) / max(len(known), 1),
            (sum(k_pass) / len(k_pass)) if k_pass else 0.0,
            len(u_pass) / max(len(unknown), 1),
        ))
    return rows


def best_at(rows, far_limit: float):
    """오수락률이 한도 이하인 것 중 **정답을 가장 많이 통과시키는** 지점."""
    ok = [r for r in rows if r[3] <= far_limit]
    if not ok:
        return None
    return max(ok, key=lambda r: r[1] * r[2])   # 통과율 × 정확도 = 실제로 건진 비율


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meetings", nargs="+", required=True, help="'회의ID:대본경로'")
    parser.add_argument("--far", type=float, default=0.01,
                        help="허용할 명단 밖 오수락률 (기본 1%%)")
    args = parser.parse_args()

    store = GlobalProfileStore()
    profiles = store.load(store.list_names())
    inference = load_speaker_embedding_inference()
    print(f"등록 프로필 {len(profiles)}명: {', '.join(sorted(profiles))}\n")

    known, unknown = [], []
    for spec in args.meetings:
        meeting, script = spec.split(":", 1)
        k, u = collect(meeting, os.path.join(_HERE, script), profiles, inference)
        print(f"  {meeting[:38]:38s} 창 {len(k):4d}개 (1등 정확도 {sum(o for o,*_ in k)/max(len(k),1):.0%})")
        known += k
        unknown += u

    print(f"\n전체 — 등록자 시행 {len(known)}창 / 명단 밖 시행 {len(unknown)}창")
    print(f"기준: 명단 밖 오수락 {args.far:.0%} 이하에서 등록자를 얼마나 건지는가\n")

    methods = [
        ("절대 유사도", 1, np.arange(0.10, 0.55, 0.025)),
        ("margin", 2, np.arange(0.0, 0.30, 0.01)),
        ("z (점수 정규화)", 3, np.arange(0.0, 4.0, 0.1)),
    ]
    print(f"{'기준':16s}{'문턱':>7s}{'통과율':>8s}{'통과분 정확도':>14s}{'오수락':>8s}{'실제로 건진 비율':>17s}")
    print("-" * 74)
    results = {}
    for label, idx, gates in methods:
        rows = sweep(known, unknown, idx, gates)
        best = best_at(rows, args.far)
        results[label] = (rows, best)
        if best is None:
            print(f"{label:16s}{'—':>7s}  (오수락 {args.far:.0%} 이하를 만족하는 문턱이 없음)")
            continue
        g, cov, acc, far = best
        print(f"{label:16s}{g:7.3f}{cov:7.0%}{acc:13.0%}{far:8.1%}{cov*acc:16.0%}")

    print("\n읽는 법")
    print("  '실제로 건진 비율' = 통과율 × 통과분 정확도. 이게 높을수록 좋은 기준이다")
    print("  (많이 통과시켜도 틀리면 소용없고, 정확해도 대부분 버리면 미상만 늘어난다)")
    print("  같은 오수락 한도에서 이 값이 높은 기준이 실제로 더 잘 가르는 것이다")

    print(f"\n{'=' * 74}\n기준별 전체 곡선 (오수락 한도를 바꿔가며 볼 때)\n{'=' * 74}")
    for label, (rows, _b) in results.items():
        print(f"\n[{label}]")
        print(f"  {'문턱':>7s}{'통과율':>8s}{'정확도':>8s}{'오수락':>8s}")
        for g, cov, acc, far in rows:
            if cov < 0.02:
                break
            print(f"  {g:7.3f}{cov:7.0%}{acc:8.0%}{far:8.1%}")


if __name__ == "__main__":
    main()
