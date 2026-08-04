"""
겹쳐 말한 구간 감지와 음원 분리가 이 서버에서 실제로 되는지 확인한다.

두 가지를 따로 본다:
  ① 겹침 감지 — 화자분리 결과만으로 계산하므로 항상 된다. 어디가 겹쳤다고 보는지,
     그게 실제로 여러 명이 말한 곳인지 눈으로 확인한다.
     (실측 사례: 대본상 전원이 "네 좋습니다"라고 한 84초 근처)
  ② 음원 분리 — 모델을 새로 받아야 하고 사용 조건 동의가 필요할 수 있다.
     **켜기 전에 여기서 되는지부터 확인할 것.** 안 되면 ①만으로 간다.

사용법:
  python probe_overlap.py --meeting <회의ID>
  python probe_overlap.py --meeting <회의ID> --separation   (분리까지 시험)
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf
import torch

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, MIN_SPEAKERS, HF_TOKEN, SEPARATION_MODEL, OVERLAP_MIN_SEC,
    OVERLAP_SEGMENT_RATIO, DIARIZATION_MODEL,
)
from stt.services.diarize_service import tracks_of  # noqa: E402
from stt.services.overlap_detect import find_overlap_spans, overlap_ratio  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--separation", action="store_true", help="음원 분리 모델까지 시험")
    args = parser.parse_args()

    meeting_dir = os.path.join(MEETINGS_DIR, args.meeting)
    audio, sr = sf.read(os.path.join(meeting_dir, args.audio), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    profiles_path = os.path.join(meeting_dir, "profiles.npz")
    enrolled = len(np.load(profiles_path).files) if os.path.isfile(profiles_path) else 0

    from pyannote.audio import Pipeline
    print("화자분리 실행 중...")
    # 앱과 같은 방식으로 로드해야 결과가 같다 (Pipeline은 token=, Model은 use_auth_token=)
    pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, token=HF_TOKEN)
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))
    # tracks_of를 쓴다 — 파이프라인이 결과를 래퍼로 감싸 주는 버전이 있어서,
    # 직접 itertracks를 부르면 터진다(앱과 같은 경로를 타야 한다)
    tracks = tracks_of(pipeline(
        {"waveform": torch.from_numpy(audio.reshape(1, -1)), "sample_rate": sr},
        min_speakers=MIN_SPEAKERS,
        max_speakers=enrolled if enrolled >= MIN_SPEAKERS else None,
    ))

    spans = find_overlap_spans(tracks)
    total = sum(end - start for start, end in spans)
    print(f"\n① 겹침 감지 (최소 {OVERLAP_MIN_SEC}초)")
    print(f"   구간 {len(spans)}개, 합계 {total:.1f}초 "
          f"(전체 {len(audio) / sr:.0f}초 중 {total / (len(audio) / sr) * 100:.1f}%)")
    for start, end in spans:
        print(f"     {start:6.1f}s ~ {end:6.1f}s  ({end - start:.1f}초)")

    # 이 겹침이 실제 회의록의 어느 발화에 걸리는지 — 화자를 못 정할 줄이 어디인지 본다
    meta_path = os.path.join(meeting_dir, "transcript.json")
    if os.path.isfile(meta_path):
        import json
        with open(meta_path, encoding="utf-8") as f:
            segments = json.load(f).get("segments") or []
        hits = [
            (seg, overlap_ratio(seg["start"], seg["end"], spans))
            for seg in segments
        ]
        marked = [(s, r) for s, r in hits if r >= OVERLAP_SEGMENT_RATIO]
        print(f"\n   '여러 명'으로 표시될 세그먼트 {len(marked)}개 "
              f"(겹침 비율 {OVERLAP_SEGMENT_RATIO:.0%} 이상)")
        for seg, ratio in marked:
            print(f"     [{seg['start']:6.1f}s] {ratio:3.0%} {seg.get('speaker') or '미상':6s} "
                  f"{seg['text'][:45]}")
        partial = [(s, r) for s, r in hits if 0 < r < OVERLAP_SEGMENT_RATIO]
        if partial:
            print(f"\n   부분 겹침(건드리지 않음) {len(partial)}개 — 화자가 여전히 명확한 경우")
            for seg, ratio in partial[:5]:
                print(f"     [{seg['start']:6.1f}s] {ratio:3.0%} {seg.get('speaker') or '미상':6s} "
                      f"{seg['text'][:45]}")

    if not args.separation:
        print("\n(--separation 을 주면 음원 분리 모델까지 시험한다)")
        return

    print(f"\n② 음원 분리 시험: {SEPARATION_MODEL}")
    from stt.services.speech_separation import separate_sources, active_channels
    result = separate_sources(audio, sr)
    if result is None:
        print("   ❌ 못 씀 — 위 경고 메시지 확인.")
        print("      대개 모델 사용 조건 미동의 또는 HF_TOKEN 문제다.")
        print("      해결이 안 되면 SEPARATION_ENABLED=0으로 두고 ①만 쓰면 된다.")
        return

    channels, _tracks = result
    print(f"   ✅ 채널 {len(channels)}개: {', '.join(channels)}")
    for start, end in spans[:5]:
        active = active_channels(channels, start, end, sr)
        print(f"     {start:6.1f}s ~ {end:6.1f}s → 소리 있는 채널 {len(active)}개: {', '.join(active)}")
    print("\n   채널 수가 참석자 수와 맞고, 겹침 구간에서 2개 이상 활성이면 정상이다.")


if __name__ == "__main__":
    main()
