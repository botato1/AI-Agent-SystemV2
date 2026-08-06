"""
겹침 감지기가 **작동은 하는지** 인공 겹침으로 확인한다.

왜 필요한가:
  겹침 처리를 만들어놨지만 지금까지 검증할 데이터가 없었다. 녹음한 회의 두 건 모두
  실제 동시 발화가 0건이었고(모델 기준), 그래서 이 기능은 **한 번도 발동한 적이 없다.**
  코드가 돌긴 하는데 "겹침이 있으면 잡는다"를 확인한 적이 없는 상태다.

  사람을 다시 모으지 않고도 최소한의 확인은 할 수 있다 — 이미 있는 녹음에서
  두 사람의 발화를 **디지털로 겹쳐** 붙이면 된다.

⚠️ 이건 진짜 겹침이 아니다. 한계를 알고 쓸 것:
  - 실제로 같은 방에서 두 사람이 말하면 서로의 목소리가 벽에 반사되고 마이크까지의
    거리가 달라 복잡하게 섞인다. 파형을 그냥 더하는 것과는 다르다.
  - 즉 이 시험을 통과해도 **실제 회의에서 잡는다는 보장은 아니다.**
  - 반대로 이걸 못 잡으면 실제로도 못 잡는다 — **실패는 확실한 정보다.**

  그래서 이 도구의 쓸모는 한쪽 방향이다: 통과하면 "적어도 배선은 됐다",
  실패하면 "실제 녹음을 기다릴 것도 없이 지금 고쳐야 한다".

사용법:
  python probe_overlap_synthetic.py --meeting <회의ID> \
      --a 15.6-23.5 --b 2.8-15.0
  (--a와 --b는 서로 다른 사람이 말한 구간)
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR  # noqa: E402
from stt.services.overlap_detect import find_overlap_spans_from_audio  # noqa: E402
from stt.services.overlap_model import load_overlap_inference  # noqa: E402


def span(text: str) -> tuple[float, float]:
    start, end = text.split("-")
    return float(start), float(end)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--a", required=True, help="화자 A 구간 '시작-끝'")
    parser.add_argument("--b", required=True, help="화자 B 구간 '시작-끝' (A와 다른 사람)")
    parser.add_argument("--part-sec", type=float, default=10.0,
                        help="각 구간(A단독/겹침/B단독)의 길이. 겹침 모델이 10초 창으로 보므로 "
                             "너무 짧으면 창 하나도 못 채워 아무것도 못 잡는다")
    parser.add_argument("--save", default=None, help="만든 오디오를 이 경로에 저장(들어보려면)")
    args = parser.parse_args()

    audio, sr = sf.read(os.path.join(MEETINGS_DIR, args.meeting, args.audio), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    a_start, a_end = span(args.a)
    b_start, b_end = span(args.b)
    a = audio[int(a_start * sr):int(a_end * sr)]
    b = audio[int(b_start * sr):int(b_end * sr)]
    if len(a) < sr or len(b) < sr:
        raise SystemExit("❌ 두 구간 모두 1초 이상이어야 한다")

    # 각 구간을 원하는 길이만큼 채운다(짧으면 반복해서 이어붙임).
    #
    # ⚠️ 길이가 중요하다. 이 모델은 10초 창 단위로 보기 때문에, 전체가 몇 초뿐이면
    #    창 하나도 못 채워 아무것도 못 잡는다 — 실제로 6.7초로 시험했다가 0%가 나왔고
    #    그건 감지기 문제가 아니라 시험 설계 문제였다.
    need = int(args.part_sec * sr)
    tile = lambda x: np.tile(x, int(np.ceil(need / len(x))))[:need]
    a, b = tile(a), tile(b)

    # [A 단독] [A+B 겹침] [B 단독] — 겹친 구간만 정확히 집어내는지 보려는 배치.
    # 앞뒤 단독 구간은 대조군이다: 거기까지 겹침이라고 하면 오탐이다.
    mixed = np.concatenate([a, np.clip(a + b, -1.0, 1.0), b])
    overlap_from = need / sr
    overlap_to = 2 * need / sr

    print(f"인공 오디오 {len(mixed)/sr:.1f}초 구성:")
    print(f"  {0:5.1f}~{overlap_from:5.1f}초  A 단독")
    print(f"  {overlap_from:5.1f}~{overlap_to:5.1f}초  **A+B 겹침** ← 여기만 잡아야 정답")
    print(f"  {overlap_to:5.1f}~{len(mixed)/sr:5.1f}초  B 단독")

    if args.save:
        sf.write(args.save, mixed, sr)
        print(f"  저장: {args.save}")

    print("\n겹침 감지 실행 중...")
    inference = load_overlap_inference()

    # 왜 못 잡는지 보려면 중간 값을 봐야 한다. 겹침 구간에서 모델이 실제로 몇 명이라고
    # 예측하는지, powerset 클래스→인원수 매핑이 맞는지 — 둘 중 하나가 틀리면 0개가 나온다.
    if inference is not None:
        import torch
        from stt.services.overlap_detect import _powerset_cardinality
        out = inference({"waveform": torch.from_numpy(mixed.reshape(1, -1)), "sample_rate": sr})
        data = np.asarray(out.data)
        spec = inference.model.specifications
        sizes = _powerset_cardinality(
            data.shape[-1], len(spec.classes), getattr(spec, "powerset_max_classes", 2),
        )
        print(f"\n[진단] 출력 형태 {data.shape} / 클래스별 인원수 매핑 {list(sizes)}")
        counts = sizes[data.argmax(axis=-1)]
        uniq, freq = np.unique(counts, return_counts=True)
        print("[진단] 예측된 동시 발화자 수 분포: "
              + ", ".join(f"{u}명 {f/counts.size:.0%}" for u, f in zip(uniq, freq)))
        # 겹침 구간에 해당하는 청크만 따로
        mid = data.shape[0] // 2
        mid_counts = counts[max(mid-1, 0):mid+2]
        u2, f2 = np.unique(mid_counts, return_counts=True)
        print("[진단] 겹침 구간 근처만: "
              + ", ".join(f"{u}명 {f/mid_counts.size:.0%}" for u, f in zip(u2, f2)))

    spans = find_overlap_spans_from_audio(mixed, inference, sr)

    print(f"\n감지된 겹침 구간 {len(spans)}개")
    for start, end in spans:
        print(f"  {start:5.1f}~{end:5.1f}초 ({end-start:.1f}초)")

    # 정답 구간을 얼마나 덮었는지 / 단독 구간을 얼마나 잘못 잡았는지
    detected = np.zeros(int(len(mixed) / sr * 10) + 1, dtype=bool)
    for start, end in spans:
        detected[int(start * 10):int(end * 10)] = True
    truth = np.zeros_like(detected)
    truth[int(overlap_from * 10):int(overlap_to * 10)] = True

    recall = (detected & truth).sum() / max(truth.sum(), 1)
    false_alarm = (detected & ~truth).sum() / max((~truth).sum(), 1)

    print(f"\n겹침 구간을 잡은 비율 : {recall:.0%}")
    print(f"단독 구간을 잘못 잡은 비율: {false_alarm:.0%}")
    print()
    if recall >= 0.5 and false_alarm <= 0.2:
        print("✅ 감지기가 작동한다. 다만 **인공 겹침이라 실제 회의에서의 성능은 별개다** —")
        print("   진짜 겹쳐 말한 녹음으로 다시 확인해야 한다.")
    elif recall < 0.5:
        print("❌ 겹쳐놓은 구간을 못 잡는다. 실제 녹음을 기다릴 것 없이 지금 고쳐야 한다.")
        print("   (인공 겹침은 실제보다 오히려 잡기 쉬운 조건이다)")
    else:
        print("⚠️ 단독 구간까지 겹침으로 본다 — 오탐이 많다. 실제 회의에 켜면 멀쩡한 발언에")
        print("   '여러 명' 표시가 붙는다.")


if __name__ == "__main__":
    main()
