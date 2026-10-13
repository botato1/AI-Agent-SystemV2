"""
정밀 모델(Qwen3-ASR)이 청크 하나를 전사하는 시간이 **어디에 쓰이는지** 쪼개 잰다.

왜 필요한가 (2026-10-13, NEXT.md 10번):
  확정 청크 지연은 정밀 모델이 청크를 통째로 전사하는 시간이고, 청크 길이에 비례한다.
  더 줄이려면 양자화·정적 캐시·compile 같은 방법이 있는데, 어느 쪽이 먹히는지는
  시간이 어디에 쓰이는지에 달려 있다:

    준비(CPU)        오디오 → 특징 추출·토큰화. 양자화로 안 줄어든다.
    인코더+프리필    오디오를 한 번에 읽는 구간. 계산량이 병목이라 양자화 효과가 작다.
    디코딩           토큰을 하나씩 생성. 토큰마다 가중치 전체를 메모리에서 읽으니
                     메모리 대역폭이 병목이면 가중치를 줄일수록(int8) 거의 비례해 빨라진다.
                     반대로 토큰당 시간이 이론 하한보다 훨씬 크면 병목은 대역폭이 아니라
                     파이썬/커널 호출 오버헤드라 양자화보다 정적 캐시·compile이 먼저다.

  분해는 모델 내부 이름에 의존하지 않도록 max_new_tokens=1 호출(≈ 인코더+프리필)과
  전체 생성의 차이로 구한다.

서버를 띄워둔 채 별도 프로세스로 모델을 하나 더 올려서 잰다(GB10은 메모리 128GB 통합).
측정 중 서버가 요청을 받고 있으면 값이 부풀려지니 **회의가 없을 때** 돌릴 것.

사용법 (GPU 서버, stt venv):
  python profile_precise_pass.py
  python profile_precise_pass.py --model Qwen/Qwen3-ASR-0.6B-hf   # 실시간용 작은 모델
"""
import argparse
import os
import statistics
import sys
import time

import numpy as np
import soundfile as sf
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    DEVICE, MEETINGS_DIR, REALTIME_SAMPLE_RATE, WHISPER_MODEL_PRECISE, build_qwen_context,
)
from stt.services.qwen_engine import Qwen3ASREngine  # noqa: E402

DEFAULT_MEETING = "ded1105f-6bcd-43fe-8f1f-b7e861b71ade_20260805-081801"


def _sync() -> float:
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    return time.perf_counter()


def load_clip(meeting: str, start_sec: float, length_sec: float) -> np.ndarray:
    audio, sr = sf.read(os.path.join(MEETINGS_DIR, meeting, "audio.wav"), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    assert sr == REALTIME_SAMPLE_RATE, f"샘플레이트 {sr} != {REALTIME_SAMPLE_RATE}"
    begin = int(start_sec * sr)
    clip = audio[begin: begin + int(length_sec * sr)]
    return clip


def breakdown(engine: Qwen3ASREngine, clip: np.ndarray, context: str | None) -> dict:
    """한 번의 전사를 준비 / 인코더+프리필 / 디코딩으로 나눠 ms로 돌려준다."""
    conv = engine._build_conversation(clip, "ko", context)

    t0 = _sync()
    inputs = engine.processor.apply_chat_template(
        [conv], tokenize=True, add_generation_prompt=True, return_dict=True,
    ).to(engine.model.device, engine.model.dtype)
    t1 = _sync()
    prompt_len = inputs["input_ids"].shape[1]

    with torch.inference_mode():
        engine.model.generate(**inputs, max_new_tokens=1, num_beams=1, do_sample=False)
    t2 = _sync()

    with torch.inference_mode():
        out = engine.model.generate(**inputs, max_new_tokens=448, num_beams=1, do_sample=False)
    t3 = _sync()

    new_tokens = int(out.shape[1] - prompt_len)
    return {
        "prep_ms": (t1 - t0) * 1000,
        "prefill_ms": (t2 - t1) * 1000,
        "full_ms": (t3 - t2) * 1000,
        "tokens": new_tokens,
        "prompt_len": int(prompt_len),
    }


def engine_total(engine: Qwen3ASREngine, clip: np.ndarray, context: str | None) -> float:
    """서버가 실제로 부르는 경로(VAD 트림·창 분할·점수 계산 포함) 전체 시간(ms)."""
    t0 = _sync()
    engine.transcribe(clip, language="ko", beam_size=1, vad_filter=True, initial_prompt=context)
    return (_sync() - t0) * 1000


def param_groups(model) -> tuple[dict, int, int]:
    groups: dict[str, int] = {}
    total = decoder = 0
    for name, p in model.named_parameters():
        nbytes = p.numel() * p.element_size()
        key = ".".join(name.split(".")[:2])
        groups[key] = groups.get(key, 0) + nbytes
        total += nbytes
        if "audio" not in name.lower():
            decoder += nbytes
    return groups, total, decoder


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=WHISPER_MODEL_PRECISE)
    ap.add_argument("--meeting", default=DEFAULT_MEETING)
    ap.add_argument("--lengths", nargs="+", type=float, default=[3, 6, 10, 15, 28])
    ap.add_argument("--start", type=float, default=5.0, help="회의 오디오에서 자를 시작 지점(초)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--bandwidth", type=float, default=273.0,
                    help="메모리 대역폭 GB/s (DGX Spark GB10 공칭값)")
    args = ap.parse_args()

    # 서버의 정밀 모델과 같은 설정: 용어 컨텍스트가 심어진 엔진
    context = build_qwen_context() if args.model == WHISPER_MODEL_PRECISE else None
    print(f"모델   : {args.model} ({DEVICE})   컨텍스트 {len(context) if context else 0}자")
    engine = Qwen3ASREngine(args.model, device=DEVICE, context=context)

    groups, total_b, decoder_b = param_groups(engine.model)
    print("\n가중치 구성 (GB):")
    for k, v in sorted(groups.items(), key=lambda kv: -kv[1])[:6]:
        print(f"  {k:40s}{v / 1e9:7.2f}")
    print(f"  {'합계':40s}{total_b / 1e9:7.2f}   (오디오 인코더 제외 디코더 쪽 {decoder_b / 1e9:.2f})")
    dtype = next(engine.model.parameters()).dtype
    print(f"  dtype {dtype}")

    # 첫 호출은 CUDA 커널 선택·메모리 할당 때문에 느리다 — 버린다
    warm = load_clip(args.meeting, args.start, 3.0)
    breakdown(engine, warm, context)
    engine_total(engine, warm, context)

    print(f"\n{'청크':>6s}{'준비':>8s}{'인코더+프리필':>12s}{'디코딩':>9s}{'토큰':>6s}"
          f"{'ms/토큰':>9s}{'엔진전체':>10s}{'RTF':>7s}")
    print("-" * 70)

    per_token = []
    for length in args.lengths:
        clip = load_clip(args.meeting, args.start, length)
        if len(clip) < int(length * REALTIME_SAMPLE_RATE * 0.95):
            print(f"{length:>5.0f}s  (오디오가 모자라 건너뜀)")
            continue
        runs = [breakdown(engine, clip, context) for _ in range(args.repeats)]
        totals = [engine_total(engine, clip, context) for _ in range(args.repeats)]

        med = lambda k: statistics.median(r[k] for r in runs)  # noqa: E731
        prep, prefill, full = med("prep_ms"), med("prefill_ms"), med("full_ms")
        tokens = int(med("tokens"))
        decode = max(full - prefill, 0.0)
        ms_tok = decode / max(tokens - 1, 1)
        eng = statistics.median(totals)
        per_token.append(ms_tok)
        print(f"{length:>5.0f}s{prep:>7.0f}ms{prefill:>11.0f}ms{decode:>8.0f}ms{tokens:>6d}"
              f"{ms_tok:>8.1f}ms{eng:>9.0f}ms{eng / 1000 / length:>7.2f}")

    if not per_token:
        return
    theory_ms = decoder_b / (args.bandwidth * 1e9) * 1000
    actual_ms = statistics.median(per_token)
    ratio = actual_ms / theory_ms if theory_ms else float("nan")
    print(f"\n토큰당 디코딩 시간: 실측 {actual_ms:.1f}ms  vs  메모리 대역폭 이론 하한 {theory_ms:.1f}ms"
          f"  ({args.bandwidth:.0f}GB/s 기준, 배율 {ratio:.1f}배)")
    print("\n읽는 법")
    print("  배율이 1~2배면 디코딩이 메모리 대역폭에 거의 붙어 있다 → 가중치를 줄이는 양자화(int8)가")
    print("    토큰당 시간을 거의 비례해서 줄인다. 양자화가 1순위.")
    print("  배율이 3배 이상이면 병목은 대역폭이 아니라 파이썬/커널 호출 오버헤드다 → 양자화는 별로")
    print("    안 줄이고, 정적 캐시 + torch.compile(또는 CUDA graph)이 먼저다.")
    print("  '인코더+프리필'이 전체의 절반 이상이면 양자화·compile 모두 효과가 제한적이다(계산량 병목).")
    print("  RTF = 엔진전체 시간 ÷ 오디오 길이. 1.0 아래면 실시간보다 빠르다.")


if __name__ == "__main__":
    main()
