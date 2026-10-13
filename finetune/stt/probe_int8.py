"""
정밀 모델(1.7B)을 int8 가중치 양자화(torchao)했을 때 속도와 전사 변화를 먼저 본다.
서버 코드는 건드리지 않는 타당성 점검용이다.

왜 필요한가 (2026-10-13, NEXT.md 10번):
  probe_static_cache.py 결과 — 정적 캐시+compile은 토큰당 24.8 → 22.0ms(−11%)에 그쳤다.
  남은 22ms 중 약 19ms는 가중치 읽기(대역폭)라서, 가중치를 줄이는 int8이 다음 후보다.
  int8 가중치 양자화는 compile 없이는 오히려 느린 경우가 흔해서 compile과 같이 잰다.

한 프로세스 안에서:
  1) 원본(bf16) dynamic으로 클립 N개의 텍스트를 뽑아 기준으로 삼고
  2) 오디오 인코더를 뺀 Linear를 int8 weight-only로 바꾼 뒤
  3) dynamic / static+compile로 토큰당 시간과 기준 대비 글자 차이를 잰다.

글자 차이는 기준 텍스트와의 편집거리 비율이다 — 정답 대비 CER이 아니라 "원본과 얼마나
달라졌나"이므로, 작아도 정확도 무영향의 증명은 아니다(채택 판단은 sweep으로 따로 한다).

필요: pip install torchao (torch 버전과 맞는 것). 없으면 안내하고 끝난다.

사용법 (GPU 서버, stt venv, 회의가 없을 때):
  python probe_int8.py
"""
import argparse
import os
import sys
import time

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from probe_static_cache import run_once  # noqa: E402
from profile_precise_pass import DEFAULT_MEETING, load_clip, param_groups  # noqa: E402
from stt.core.config import DEVICE, WHISPER_MODEL_PRECISE, build_qwen_context  # noqa: E402
from stt.services.qwen_engine import Qwen3ASREngine  # noqa: E402


def edit_ratio(a: str, b: str) -> float:
    """편집거리 / 기준 길이."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(len(a), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", default=DEFAULT_MEETING)
    ap.add_argument("--starts", nargs="+", type=float, default=[5, 25, 45, 65, 85])
    ap.add_argument("--length", type=float, default=12.0)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    try:
        import torchao
        from torchao.quantization import quantize_
        try:
            from torchao.quantization import Int8WeightOnlyConfig as _Cfg
        except ImportError:  # 구버전 이름
            from torchao.quantization import int8_weight_only as _Cfg
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"torchao를 못 불러왔다: {exc}\n"
            f"  torch {torch.__version__} / python {sys.version.split()[0]}에 맞는 버전을 설치해야 한다.\n"
            f"  (설치 전 확인: pip index versions torchao)"
        )
    print(f"torch {torch.__version__} / torchao {getattr(torchao, '__version__', '?')}")

    context = build_qwen_context()
    engine = Qwen3ASREngine(WHISPER_MODEL_PRECISE, device=DEVICE, context=context)
    clips = [load_clip(args.meeting, st, args.length) for st in args.starts]

    run_once(engine, clips[0], context, "dynamic")  # 워밍업
    base = []
    for c in clips:
        _ms, _n, text = run_once(engine, c, context, "dynamic")
        base.append(text)

    _g, total_before, decoder_before = param_groups(engine.model)

    def only_decoder_linear(module, fqn):
        return isinstance(module, torch.nn.Linear) and "audio" not in fqn.lower()

    t0 = time.perf_counter()
    quantize_(engine.model, _Cfg(), filter_fn=only_decoder_linear)
    print(f"양자화 {time.perf_counter() - t0:.1f}s")
    torch.cuda.empty_cache()
    _g, total_after, _d = param_groups(engine.model)
    print(f"가중치 {total_before / 1e9:.2f}GB → {total_after / 1e9:.2f}GB (파라미터 기준)")

    print(f"\n{'모드':<16}{'호출':>5}{'ms/토큰':>10}{'평균 글자변화':>14}")
    print("-" * 48)
    for mode in ("dynamic", "static+compile"):
        for i in range(args.repeats):
            ms_tok, diffs = [], []
            for c, ref in zip(clips, base):
                try:
                    ms, ntok, text = run_once(engine, c, context, mode)
                except Exception as exc:  # noqa: BLE001
                    print(f"{mode:<16}{i + 1:>5}  실패: {type(exc).__name__}: {str(exc)[:100]}")
                    ms_tok = None
                    break
                ms_tok.append(ms / max(ntok, 1))
                diffs.append(edit_ratio(ref, text))
            if ms_tok is None:
                break
            tag = "  (첫 호출: 컴파일 포함)" if mode != "dynamic" and i == 0 else ""
            print(f"{mode:<16}{i + 1:>5}{sum(ms_tok) / len(ms_tok):>9.1f}ms{100 * sum(diffs) / len(diffs):>12.1f}%{tag}")

    print("\n읽는 법")
    print("  기준(bf16 dynamic)은 앞서 24.7~25.0ms/토큰, static+compile만으로는 22.0ms였다.")
    print("  int8+compile이 15ms 안팎이면 이론치(−39%)에 가깝고, 22ms에서 안 내려오면 가중치 읽기가")
    print("  병목이 아니었거나 int8 커널이 이 GPU에서 대역폭을 못 쓴다는 뜻이다.")
    print("  글자 변화가 1~2% 이내면 sweep(순수 전사 오류 +1%p 기준)으로 넘어갈 만하다.")


if __name__ == "__main__":
    main()
