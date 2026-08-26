"""
재분석 파이프라인의 **단계별로 무엇을 잃는지** 본다.

왜 필요한가 (2026-08-13):
  짧은 발언이 자기 세그먼트를 잃고 옆 사람 발언에 흡수된다. 회의 ba8f38c4에서
  대본 23줄 중 7줄이 그렇게 사라졌고, 그 말들은 **다른 사람 이름으로 기록**됐다.
  모순 감지 제품에서 "네 그렇게 하죠"와 "아니요 그건 아닌데요"는 지워도 되는
  맞장구가 아니라 **의사결정 자체**다.

  타임라인 해상도(창 1.5초 / 3창 평활 / 최소조각 1.0초)를 의심해 네 조합을 재봤지만
  **미상 7건이 전부 그대로였다** — 원인이 거기가 아니다.

  그런데 흡수된 것 중엔 **3초짜리 발언**도 있다("저도 같은 생각이에요", 20.1~23.1초).
  3초면 어떤 최소 길이 문턱에도 안 걸린다. 즉 문턱 문제가 아니라 **더 앞 단계에서
  그 구간이 옆 사람 것으로 판정되고 있다**는 뜻이다.

  파이프라인은 네 단계를 거치는데, 지금까지 마지막 단계만 봤다:
    ① 화자분리(pyannote)      — 애초에 턴으로 잡았나
    ② 같은 화자 인접 턴 병합   — 옆 턴에 흡수됐나
    ③ 겹치는 턴 정리          — 긴 턴 우선 정책이 버렸나
    ④ 타임라인으로 재분할      — 다시 나눠줬어야 하는데 못 했나

  각 단계에서 관심 구간이 어떻게 변하는지 찍어보면 어디서 잃는지 한 번에 보인다.

사용법:
  python probe_turn_pipeline.py --meeting <회의ID> --at 20.1-23.1 --expect 이승주
  python probe_turn_pipeline.py --meeting <회의ID> --script scripts/xxx.txt   # 대본 전체 자동
"""
import argparse
import asyncio
import os
import sys

import numpy as np
import soundfile as sf

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR, MIN_SPEAKERS  # noqa: E402
from stt.services.diarize_service import run_diarization  # noqa: E402
from stt.services.refine_service import (  # noqa: E402
    _merge_adjacent_turns, _resolve_overlapping_turns,
)
from stt.services.speaker_timeline import (  # noqa: E402
    build_speaker_timeline, split_turns_by_timeline,
)
from stt.services.speaker_id_service import load_speaker_embedding_inference  # noqa: E402


def overlapping(turns, start, end):
    """관심 구간과 겹치는 턴만 — 회의 전체를 찍으면 읽을 수가 없다."""
    return [t for t in turns
            if min(t["end"], end) - max(t["start"], start) > 0.05]


def show(label, turns, start, end, expect):
    hits = overlapping(turns, start, end)
    print(f"\n[{label}] 이 구간에 걸친 턴 {len(hits)}개")
    for t in hits:
        mark = "✅" if t.get("speaker") == expect else "  "
        covers = min(t["end"], end) - max(t["start"], start)
        print(f"  {mark} {t['start']:6.1f}~{t['end']:6.1f} ({t['end']-t['start']:5.1f}초) "
              f"{str(t.get('speaker')):10s} 이 구간을 {covers:.1f}초 덮음")
    if not hits:
        print("     (없음 — 이 단계에서 구간이 사라졌다)")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--at", required=True, help="관심 구간 '시작-끝'(초)")
    parser.add_argument("--expect", required=True, help="이 구간에서 실제로 말한 사람")
    args = parser.parse_args()

    start, end = (float(x) for x in args.at.split("-"))
    meeting_dir = os.path.join(MEETINGS_DIR, args.meeting)
    audio, sr = sf.read(os.path.join(meeting_dir, "audio.wav"), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    profiles_path = os.path.join(meeting_dir, "profiles.npz")
    data = np.load(profiles_path)
    profiles = {n: data[n] for n in data.files}
    print(f"회의 {args.meeting}")
    print(f"관심 구간 {start}~{end}초 — 실제 발화자: {args.expect}")
    print(f"프로필 {len(profiles)}명: {', '.join(sorted(profiles))}")

    import torch
    from pyannote.audio import Pipeline
    # Pipeline은 token=, Model은 use_auth_token= 으로 인자 이름이 다르다(main.py와 동일)
    from stt.core.config import DIARIZATION_MODEL, HF_TOKEN
    pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, token=HF_TOKEN)
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))
    waveform = {"waveform": torch.from_numpy(audio.reshape(1, -1)), "sample_rate": sr}

    tracks = await run_diarization(
        pipeline, waveform,
        max_speakers=len(profiles) if len(profiles) >= MIN_SPEAKERS else None,
    )
    # ① 화자분리 결과는 익명 라벨(SPEAKER_00…)이라 이름 비교가 안 된다.
    #    구간을 잡았는지만 본다.
    show("① 화자분리", tracks, start, end, expect=None)

    merged = _merge_adjacent_turns(tracks)
    show("② 같은 화자 병합", merged, start, end, expect=None)

    resolved = _resolve_overlapping_turns(merged)
    show("③ 겹침 정리", resolved, start, end, expect=None)

    inference = load_speaker_embedding_inference()
    timeline = build_speaker_timeline(audio, profiles, inference, sr)
    print(f"\n[타임라인] 이 구간의 판정 (0.5초 간격)")
    t = start
    while t < end:
        who = timeline.speaker_of(t, t + 0.5)
        mark = "✅" if who == args.expect else ("  " if who else "△ ")
        print(f"  {mark} {t:6.1f}~{t+0.5:5.1f}  {who or '미상'}")
        t += 0.5

    final = split_turns_by_timeline(resolved, timeline)
    show("④ 타임라인 재분할(최종)", final, start, end, expect=args.expect)

    print("\n" + "=" * 72)
    print("읽는 법")
    print("  ①에 구간이 없다 → 화자분리가 애초에 발화로 안 잡았다(오디오/VAD 문제)")
    print("  ①엔 있는데 ②에서 옆 턴에 흡수 → 화자분리가 옆 사람과 같은 라벨로 봤다")
    print("  ②→③에서 사라짐 → 겹침 정리의 '긴 턴 우선'이 버렸다")
    print("  ③까지 남았는데 ④에서 못 나눔 → 타임라인이 이 구간을 옆 사람으로 봤다")
    print("     (타임라인 출력에서 실제 발화자가 몇 칸이나 잡혔는지 확인할 것)")


if __name__ == "__main__":
    asyncio.run(main())
