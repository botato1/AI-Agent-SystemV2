"""
겹침을 **화자분리 결과에서 역산하지 말고 모델에게 직접 물어본다.**

지금까지의 방식과 무엇이 다른가:
  overlap_detect는 화자분리(클러스터링까지 끝난 결과)에서 구간이 겹치는지를 본다.
  그런데 그 단계에서는 "이 순간 몇 명이 말하는가"라는 원래 정보가 이미 뭉개져 있다.
  실측에서 대본상 **전원**이 답한 구간도 2명으로만 잡혔고, 그래서 맞장구(2명)와
  구분이 안 됐다 — 3명 이상 동시 발화가 0건이었다.

  pyannote의 segmentation-3.0은 화자분리가 **내부적으로 쓰는** 모델이고,
  프레임 단위로 "지금 누가 말하는가"를 직접 예측한다(powerset 분류).
  클러스터링 전 단계라 동시 발화 정보가 살아 있다. 이미 받아져 있어 권한 문제도 없다.

이 스크립트는 그 예측이 실제로 맞장구와 전원 응답을 갈라주는지만 확인한다.
갈라주면 overlap_detect의 근거를 이쪽으로 바꾸고, 못 갈라주면 겹침 처리는
지금 수준(표시만)에서 멈춘다. **만들기 전에 잰다.**

사용법:
  python probe_overlap_frames.py --meeting <회의ID>
  python probe_overlap_frames.py --meeting <회의ID> --at 84.1 113.5 199.2
"""
import argparse
import itertools
import json
import os
import sys

import numpy as np
import soundfile as sf
import torch

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR, HF_TOKEN  # noqa: E402

_SEGMENTATION_MODEL = "pyannote/segmentation-3.0"


def powerset_cardinality(num_classes: int, max_speakers: int, max_concurrent: int) -> np.ndarray:
    """
    powerset 클래스 번호 → 그 클래스가 뜻하는 '동시 발화자 수'.

    pyannote는 화자 조합을 하나의 클래스로 본다: {} / {0} / {1} / {2} / {0,1} / ...
    클래스 순서는 카디널리티 오름차순, 같은 카디널리티 안에서는 조합 순서다.
    pyannote 내부 클래스를 쓸 수 있으면 그걸 쓰고, 없으면 같은 규칙으로 만든다.
    """
    try:
        from pyannote.audio.utils.powerset import Powerset
        mapping = Powerset(max_speakers, max_concurrent).mapping  # (클래스수, 화자수)
        return np.asarray(mapping).sum(axis=1)
    except Exception:
        sizes = []
        for k in range(max_concurrent + 1):
            for combo in itertools.combinations(range(max_speakers), k):
                sizes.append(len(combo))
        if len(sizes) != num_classes:
            raise SystemExit(
                f"❌ powerset 클래스 수가 안 맞는다 (모델 {num_classes} vs 계산 {len(sizes)}) — "
                f"pyannote 버전이 다른 듯. 이 방식은 여기서 중단."
            )
        return np.asarray(sizes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--at", nargs="*", type=float, default=None,
                        help="자세히 볼 시각(초). 생략하면 회의록 세그먼트 전체를 훑는다")
    args = parser.parse_args()

    meeting_dir = os.path.join(MEETINGS_DIR, args.meeting)
    audio, sr = sf.read(os.path.join(meeting_dir, args.audio), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    from pyannote.audio import Model, Inference
    print(f"모델 로드: {_SEGMENTATION_MODEL}")
    model = Model.from_pretrained(_SEGMENTATION_MODEL, use_auth_token=HF_TOKEN)
    spec = model.specifications
    max_speakers = len(spec.classes)
    max_concurrent = getattr(spec, "powerset_max_classes", 2)
    print(f"  로컬 최대 화자 {max_speakers}명, 동시 최대 {max_concurrent}명")

    inference = Inference(model, duration=5.0, step=0.5)
    if torch.cuda.is_available():
        inference.to(torch.device("cuda"))

    print("프레임 단위 예측 중...")
    output = inference({"waveform": torch.from_numpy(audio.reshape(1, -1)), "sample_rate": sr})
    data = np.asarray(output.data)          # (프레임수, 클래스수)
    frames = output.sliding_window

    sizes = powerset_cardinality(data.shape[-1], max_speakers, max_concurrent)
    # 프레임마다 가장 확률이 높은 조합을 고르고, 그 조합의 인원수를 센다
    counts = sizes[data.argmax(axis=-1)]

    def speakers_at(start: float, end: float) -> tuple[float, int, float]:
        """구간의 (평균 동시 화자 수, 최대, 2명 이상인 시간 비율)."""
        i0 = max(int((start - frames.start) / frames.step), 0)
        i1 = min(int((end - frames.start) / frames.step) + 1, len(counts))
        window = counts[i0:i1]
        if not len(window):
            return 0.0, 0, 0.0
        return float(window.mean()), int(window.max()), float((window >= 2).mean())

    print(f"\n{'=' * 78}")
    if args.at:
        print(f"{'시각':>8s}{'평균':>7s}{'최대':>5s}{'2명이상 비율':>13s}")
        for time in args.at:
            mean, peak, ratio = speakers_at(time, time + 1.5)
            print(f"{time:8.1f}{mean:7.2f}{peak:5d}{ratio:12.0%}")
        return

    meta_path = os.path.join(meeting_dir, "transcript.json")
    if not os.path.isfile(meta_path):
        raise SystemExit("❌ 회의록이 없다 — --at 으로 시각을 직접 지정할 것")
    with open(meta_path, encoding="utf-8") as f:
        segments = json.load(f).get("segments") or []

    print(f"{'시작':>8s}{'평균':>7s}{'최대':>5s}{'2명↑':>7s}  {'화자':8s} 텍스트")
    print("-" * 78)
    for seg in segments:
        mean, peak, ratio = speakers_at(seg["start"], seg["end"])
        flag = " ←" if ratio >= 0.5 else "  "
        print(f"{seg['start']:8.1f}{mean:7.2f}{peak:5d}{ratio:6.0%}{flag}"
              f"{(seg.get('speaker') or '미상'):8s} {seg['text'][:38]}")

    print(f"\n{'=' * 78}")
    print("판단 기준:")
    print("  대본상 '전원'이 말한 줄(84.1s '네 좋습니다')의 평균/최대가")
    print("  맞장구 줄(113.5s '시연 전에', 199.2s 가동현)보다 **뚜렷이 높아야** 한다.")
    print("  그래야 둘을 가를 문턱이 존재한다.")
    print("  비슷하면 이 방식도 못 가르는 것이므로, 겹침 처리는 표시만 하는 지금 수준에서 멈춘다.")


if __name__ == "__main__":
    main()
