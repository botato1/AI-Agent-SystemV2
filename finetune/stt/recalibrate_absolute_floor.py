"""
다중 회의 등록(C) 채택 이후 `SPEAKER_ABSOLUTE_FLOOR`(현재 0.35)를 한 번도
재계산한 적이 없다는 게 2026-09-07 실측(NEXT.md 4a)에서 드러났다 — 그때는
명단 밖 오수락이 세 회의 합쳐 11/11(100%)이었다. `probe_out_of_roster.py`는
--truth를 사람이 손으로(초 단위) 넣어야 해서 회의 하나 재는 데도 시간이 든다.

이 스크립트는 `sweep_speaker_floor.py`의 `truth_spans()`(대본 정렬로 발화
구간을 자동으로 찾는 함수)를 재사용해서, **여러 회의·여러 화자에 대해
자동으로 leave-one-out을 돌리고 결과를 전부 풀링**한다. 각 화자를 한 번씩
명단에서 뺀 뒤:
  - 그 화자 본인의 발화 구간 → "명단 밖" 표본
  - 같은 회의의 나머지 화자들의 발화 구간(같은 명단 상태로) → "명단 안" 표본
을 모아서, 전체 데이터로 안/밖이 갈리는 바닥값을 다시 찾는다.

사용법:
  python recalibrate_absolute_floor.py \
      --meeting ded1105f-6bcd-43fe-8f1f-b7e861b71ade_20260805-081801:scripts/launch_plan_meeting.txt \
      --meeting ba8f38c4-2eba-4049-ae1d-a0f66533e131_20260812-062851:scripts/search_quality_meeting.txt \
      --meeting 8b5f84b7-5e29-46f5-bb67-158980a5f352_20260805-064739:scripts/retention_meeting.txt
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

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, SPEAKER_WINDOW_SEC, SPEAKER_WINDOW_HOP_SEC,
)
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)
from evaluate_against_script import load_script, align  # noqa: E402


def truth_spans(meeting: str, script_path: str, speaker: str) -> list[tuple[float, float]]:
    """sweep_speaker_floor.py와 동일한 방식 — 실시간 전사(정답이 흔들리지 않음)를
    대본과 정렬해 특정 화자의 발화 구간을 찾는다."""
    import json
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


def window_top1_scores(identifier: LiveSpeakerIdentifier, audio: np.ndarray, sr: int,
                        spans: list[tuple[float, float]]) -> list[float]:
    win, hop = int(SPEAKER_WINDOW_SEC * sr), int(SPEAKER_WINDOW_HOP_SEC * sr)
    scores = []
    for start, end in spans:
        seg = audio[int(start * sr):int(end * sr)]
        for off in range(0, max(len(seg) - win + 1, 1), hop):
            clip = seg[off:off + win]
            if len(clip) < win // 2:
                break
            ranked = identifier.rank_profiles(identifier.extract_embedding(clip))
            scores.append(ranked[0][0])
    return scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", action="append", required=True,
                     help="'회의ID:대본경로' 형태, 여러 번 줄 수 있음")
    ap.add_argument("--names", nargs="+", default=None,
                     help="전역 프로필 중 이 회의들에 실제로 참여한 사람만 좁히고 싶을 때. "
                          "생략하면 전역 등록 전원을 기본 명단으로 쓴다")
    args = ap.parse_args()

    store = GlobalProfileStore()
    full_roster = args.names or store.list_names()
    embed_model = load_speaker_embedding_inference()

    inside_all: list[float] = []
    outside_all: list[float] = []

    for spec in args.meeting:
        meeting, script_path = spec.split(":", 1)
        audio, sr = sf.read(os.path.join(MEETINGS_DIR, meeting, "audio.wav"), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        script = load_script(os.path.expanduser(script_path))
        participants = sorted({line["speaker"] for line in script if not line["overlapped"]})
        participants = [p for p in participants if p in full_roster]

        print(f"\n=== {meeting} — 참석자 {participants} ===")

        for excluded in participants:
            roster = [n for n in full_roster if n != excluded]
            profiles = store.load(roster)
            identifier = LiveSpeakerIdentifier(embed_model, initial_profiles=profiles)

            out_spans = truth_spans(meeting, script_path, excluded)
            out_scores = window_top1_scores(identifier, audio, sr, out_spans)
            outside_all.extend(out_scores)

            for other in participants:
                if other == excluded:
                    continue
                in_spans = truth_spans(meeting, script_path, other)
                in_scores = window_top1_scores(identifier, audio, sr, in_spans)
                inside_all.extend(in_scores)

            print(f"  {excluded} 제외 — 명단 밖 창 {len(out_scores)}개, "
                  f"평균 {np.mean(out_scores) if out_scores else float('nan'):.3f}")

    if not inside_all or not outside_all:
        raise SystemExit("❌ 명단 안/밖 표본이 둘 다 있어야 한다 — truth_spans가 비어있지 않은지 확인")

    print(f"\n{'=' * 60}")
    print(f"전체 풀링 결과 — 명단 안 창 {len(inside_all)}개 / 명단 밖 창 {len(outside_all)}개")
    print(f"명단 안 1등 유사도: 평균 {np.mean(inside_all):.3f}, 하위 5% {np.percentile(inside_all, 5):.3f}")
    print(f"명단 밖 1등 유사도: 평균 {np.mean(outside_all):.3f}, 상위 5% {np.percentile(outside_all, 95):.3f}")

    print(f"\n바닥값 후보 (SPEAKER_ABSOLUTE_FLOOR 후보, 현재 배포값 0.35)")
    print(f"{'바닥':>6s}{'명단 안 유지':>13s}{'명단 밖 차단':>13s}")
    best_floor, best_sum = None, -1
    for floor in np.arange(0.10, 0.55, 0.025):
        keep = sum(s >= floor for s in inside_all) / len(inside_all) * 100
        block = sum(s < floor for s in outside_all) / len(outside_all) * 100
        marker = ""
        if keep + block > best_sum:
            best_sum, best_floor = keep + block, floor
            marker = "  <- 유지+차단 합 최대"
        print(f"{floor:6.3f}{keep:12.0f}%{block:12.0f}%{marker}")

    print(f"\n현재 배포값 0.35와 비교해 EER 근사 지점(유지+차단 합이 최대인 곳): {best_floor:.3f}")
    print("읽는 법: 두 분포가 갈리면 이 지점 근처에서 유지율은 높게, 차단율도 높게 나온다.")
    print("두 분포가 겹치면(어디를 잡아도 유지·차단이 둘 다 낮으면) 바닥값만으로는 못 가른다는 뜻.")


if __name__ == "__main__":
    main()
