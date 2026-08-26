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
    MEETINGS_DIR, MIN_SPEAKERS, HF_TOKEN, SEPARATION_MODEL,
    OVERLAP_SEGMENT_RATIO, DIARIZATION_MODEL,
)
from stt.services.diarize_service import tracks_of  # noqa: E402
from stt.services.overlap_detect import (  # noqa: E402
    find_overlap_spans, find_overlap_spans_from_audio, overlap_ratio, concurrent_speakers,
)
from stt.services.overlap_model import load_overlap_inference  # noqa: E402


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

    # 동시 화자 수를 몇 명부터 겹침으로 볼지에 따라 결과가 크게 달라진다.
    # 2명 기준은 "맞장구"까지 걸려서 맞는 이름을 지운다 — 그래서 나란히 놓고 고른다.
    import json
    meta_path = os.path.join(meeting_dir, "transcript.json")
    segments = []
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            segments = json.load(f).get("segments") or []

    for min_speakers in (2, 3, 4):
        spans = find_overlap_spans(tracks, min_speakers)
        total = sum(end - start for start, end in spans)
        print(f"\n{'=' * 72}")
        print(f"동시 화자 {min_speakers}명 이상 → 겹침 구간 {len(spans)}개, 합계 {total:.1f}초 "
              f"({total / (len(audio) / sr) * 100:.1f}%)")

        if not segments:
            for start, end in spans:
                print(f"     {start:6.1f}s ~ {end:6.1f}s  ({end - start:.1f}초)")
            continue

        marked = [
            (seg, overlap_ratio(seg["start"], seg["end"], spans))
            for seg in segments
            if overlap_ratio(seg["start"], seg["end"], spans) >= OVERLAP_SEGMENT_RATIO
        ]
        print(f"'여러 명'으로 표시될 세그먼트 {len(marked)}개 "
              f"(겹침 {OVERLAP_SEGMENT_RATIO:.0%} 이상)")
        for seg, ratio in marked:
            peak = concurrent_speakers(tracks, seg["start"], seg["end"])
            print(f"   [{seg['start']:6.1f}s] 겹침{ratio:3.0%} 동시{peak}명 "
                  f"{seg.get('speaker') or '미상':6s} {seg['text'][:40]}")

    # 모델에 직접 물은 결과 — 운영 경로가 쓰는 방식이다.
    print(f"\n{'=' * 72}")
    print("모델에 직접 질의 (segmentation-3.0, 운영 경로가 쓰는 방식)")
    model_spans = find_overlap_spans_from_audio(audio, load_overlap_inference(), sr)
    total = sum(end - start for start, end in model_spans)
    print(f"겹침 구간 {len(model_spans)}개, 합계 {total:.1f}초 "
          f"({total / (len(audio) / sr) * 100:.1f}%)")
    for start, end in model_spans:
        print(f"     {start:6.1f}s ~ {end:6.1f}s  ({end - start:.1f}초)")
    if segments:
        marked = [
            (seg, overlap_ratio(seg["start"], seg["end"], model_spans))
            for seg in segments
            if overlap_ratio(seg["start"], seg["end"], model_spans) >= OVERLAP_SEGMENT_RATIO
        ]
        print(f"'겹침'으로 표시될 세그먼트 {len(marked)}개")
        for seg, ratio in marked:
            print(f"   [{seg['start']:6.1f}s] 겹침{ratio:3.0%} "
                  f"{seg.get('speaker') or '미상':6s} {seg['text'][:40]}")

    print(f"\n{'=' * 72}")
    print("두 방식 비교:")
    print("  화자분리 역산은 턴 경계가 살짝 겹친 것까지 동시 발화로 읽어 오탐이 많다")
    print("  (실측: 그 방식이 찾은 11개가 모델 기준으로는 하나도 겹침이 아니었다).")
    print("  모델 질의 쪽이 0개라면 이 회의에 진짜 겹침이 없다는 뜻이고,")
    print("  그러면 겹침 기능은 이 녹음으로 검증할 수 없다 — 일부러 겹쳐 말한 녹음이 필요하다.")
    print()
    print("고르는 법:")
    print("  이 목록의 각 줄이 **정말로 여러 명이 한꺼번에 말한 곳인지** 대본과 대조할 것.")
    print("  맞는 이름이 붙어 있던 줄이 목록에 있으면 그건 손해다 —")
    print("  오배정 하나를 고치려고 정답을 여러 개 버리게 된다.")
    print("  목록이 '전원이 답한 줄'만 남는 문턱을 고르면 된다.")

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
    # model_spans를 쓴다 — 위 반복문의 마지막 값(4명 기준, 항상 비어 있음)이 아니라
    # 운영 경로가 실제로 쓰는 겹침 구간이어야 의미가 있다
    for start, end in model_spans[:5]:
        active = active_channels(channels, start, end, sr)
        print(f"     {start:6.1f}s ~ {end:6.1f}s → 소리 있는 채널 {len(active)}개: {', '.join(active)}")
    print("\n   채널 수가 참석자 수와 맞고, 겹침 구간에서 2개 이상 활성이면 정상이다.")


if __name__ == "__main__":
    main()
