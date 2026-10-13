"""
정적 KV 캐시 / torch.compile이 이 서버(GB10, aarch64, sm_121)에서 되는지, 되면 토큰당
시간이 얼마나 줄고 **전사 결과가 그대로인지** 먼저 확인한다. 속도 최적화를 코드에 넣기 전의
타당성 점검용이다 — 이 스크립트는 서버 코드를 건드리지 않는다.

왜 필요한가 (2026-10-13, NEXT.md 10번 4단계):
  정밀 모델 토큰당 24.3ms 중 약 5ms는 파이썬/커널 호출 오버헤드다. 정적 캐시 +
  torch.compile(또는 CUDA graph)이 이 부분을 겨냥한다. 가능한지, 얼마나 먹히는지,
  그리고 **청크 길이가 바뀔 때마다 다시 컴파일되는지**가 관건이다 — 실시간 청크는 길이가
  매번 달라서, 재컴파일이 몇 초씩 걸리면 오히려 지연이 늘어난다.

세 가지 모드를 같은 클립으로 비교한다:
  dynamic        지금 서버가 쓰는 방식(기준)
  static         정적 캐시, compile 끔 — 캐시 방식만 바꾼 효과
  static+compile 정적 캐시 + 자동 compile

각 모드·길이마다 같은 클립을 3번 돌려 첫 호출(컴파일/워밍업 포함)과 이후 호출을 나눠 보여준다.
전사 텍스트가 dynamic과 다르면 표시한다(무손실이라고 믿으면 안 되는 이유).

서버를 띄워둔 채 별도 프로세스로 모델을 하나 더 올린다. 회의가 없을 때 돌릴 것.

사용법 (GPU 서버, stt venv):
  python probe_static_cache.py
  python probe_static_cache.py --lengths 4 8 12 --repeats 3
"""
import argparse
import os
import sys
import time
import traceback

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from profile_precise_pass import DEFAULT_MEETING, load_clip  # noqa: E402
from stt.core.config import DEVICE, WHISPER_MODEL_PRECISE, build_qwen_context  # noqa: E402
from stt.services.qwen_engine import Qwen3ASREngine  # noqa: E402

_MAX_NEW_TOKENS = 448


def _sync() -> float:
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    return time.perf_counter()


def run_once(engine: Qwen3ASREngine, clip, context, mode: str):
    """(전체 ms, 새 토큰 수, 텍스트). mode별 generate 인자만 다르다."""
    inputs = engine.processor.apply_chat_template(
        [engine._build_conversation(clip, "ko", context)],
        tokenize=True, add_generation_prompt=True, return_dict=True,
    ).to(engine.model.device, engine.model.dtype)
    prompt_len = inputs["input_ids"].shape[1]

    extra = {}
    if mode == "static":
        extra = {"cache_implementation": "static", "disable_compile": True}
    elif mode == "static+compile":
        extra = {"cache_implementation": "static"}

    t0 = _sync()
    with torch.inference_mode():
        out = engine.model.generate(
            **inputs, max_new_tokens=_MAX_NEW_TOKENS, num_beams=1, do_sample=False, **extra,
        )
    ms = (_sync() - t0) * 1000
    ids = out[:, prompt_len:]
    text = engine.processor.decode(ids, return_format="transcription_only")[0].strip()
    return ms, int(ids.shape[1]), text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=WHISPER_MODEL_PRECISE)
    ap.add_argument("--meeting", default=DEFAULT_MEETING)
    ap.add_argument("--lengths", nargs="+", type=float, default=[6, 10, 15])
    ap.add_argument("--start", type=float, default=5.0)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    context = build_qwen_context() if args.model == WHISPER_MODEL_PRECISE else None
    print(f"torch {torch.__version__} / cuda {torch.version.cuda} / 디바이스 {DEVICE}")
    if torch.cuda.is_available():
        print(f"GPU {torch.cuda.get_device_name(0)} capability {torch.cuda.get_device_capability(0)}")
    try:
        import triton
        print(f"triton {triton.__version__}")
    except Exception as exc:  # noqa: BLE001
        print(f"triton 없음/로드 실패: {exc}  → torch.compile(inductor)이 안 될 가능성이 높다")

    engine = Qwen3ASREngine(args.model, device=DEVICE, context=context)

    # 워밍업: 첫 호출의 CUDA 초기화 비용을 기준 측정에서 빼기 위해
    run_once(engine, load_clip(args.meeting, args.start, 3.0), context, "dynamic")

    baseline_text: dict[float, str] = {}
    print(f"\n{'모드':<16}{'길이':>5}{'호출':>5}{'시간':>9}{'토큰':>6}{'ms/토큰':>9}  비고")
    print("-" * 70)
    for mode in ("dynamic", "static", "static+compile"):
        for length in args.lengths:
            clip = load_clip(args.meeting, args.start, length)
            for i in range(args.repeats):
                try:
                    ms, ntok, text = run_once(engine, clip, context, mode)
                except Exception as exc:  # noqa: BLE001
                    print(f"{mode:<16}{length:>4.0f}s{i + 1:>5}   실패: {type(exc).__name__}: {str(exc)[:90]}")
                    if i == 0:
                        traceback.print_exc(limit=3)
                    break
                note = ""
                if mode == "dynamic" and i == 0:
                    baseline_text[length] = text
                elif length in baseline_text and text != baseline_text[length]:
                    note = "⚠️ 텍스트가 dynamic과 다름"
                    if i == 0:
                        print(f"      dynamic : {baseline_text[length]}")
                        print(f"      {mode:<8}: {text}")
                if i == 0 and mode != "dynamic":
                    note = (note + " 첫 호출(컴파일 포함)").strip()
                print(f"{mode:<16}{length:>4.0f}s{i + 1:>5}{ms:>8.0f}ms{ntok:>6d}{ms / max(ntok, 1):>8.1f}ms  {note}")

    print("\n읽는 법")
    print("  호출 2·3번의 ms/토큰이 dynamic보다 확실히 작고 텍스트가 같으면 도입 후보다.")
    print("  길이가 바뀔 때마다 '첫 호출'이 수 초씩 걸리면(재컴파일) 실시간 청크에는 못 쓴다 —")
    print("  그 경우 캐시 길이를 고정값으로 패딩하는 방식을 따로 검토해야 한다.")


if __name__ == "__main__":
    main()
