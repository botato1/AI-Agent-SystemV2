"""
서버가 실제로 부르는 경로(Qwen3ASREngine.transcribe)로 int8 인스턴스(fast_decode=True)를
bf16 인스턴스와 비교한다. probe_int8.py가 generate를 직접 불러 잰 것과 달리, 이건
VAD 트림·창 분할·avg_logprob 계산·컨텍스트까지 서버와 같은 길을 지난다.

확인하는 것:
  1) 속도 — 같은 클립 전사 시간(bf16 vs int8)
  2) 텍스트 차이 — 기준(bf16) 대비 편집거리, 그리고 avg_logprob 차이(신뢰도 게이트 입력)
  3) 동시 호출 — 화자 전환 때 턴별 전사가 스레드로 병렬 호출된다. 정적 캐시가 겹치면
     결과가 깨지므로, 같은 클립을 여러 스레드가 동시에 돌려도 단독 결과와 같은지 본다.

메모리: 모델을 두 개 올린다(GB10 128GB 통합). 서버가 떠 있어도 되지만 회의 중엔 피할 것.

사용법 (GPU 서버, stt venv; torchao 설치 필요):
  python probe_engine_int8.py
"""
import argparse
import os
import sys
import threading
import time

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from probe_int8 import edit_ratio  # noqa: E402
from profile_precise_pass import DEFAULT_MEETING, load_clip  # noqa: E402
from stt.core.config import DEVICE, WHISPER_MODEL_PRECISE, build_qwen_context  # noqa: E402
from stt.services.qwen_engine import Qwen3ASREngine  # noqa: E402


def run(engine, clip, context):
    t0 = time.perf_counter()
    segs, _ = engine.transcribe(clip, language="ko", beam_size=1, vad_filter=True, initial_prompt=context)
    ms = (time.perf_counter() - t0) * 1000
    text = " ".join(s.text for s in segs)
    lp = sum(s.avg_logprob for s in segs) / len(segs) if segs else 0.0
    return ms, text, lp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", default=DEFAULT_MEETING)
    ap.add_argument("--starts", nargs="+", type=float, default=[5, 20, 35, 50, 65, 80])
    ap.add_argument("--length", type=float, default=12.0)
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()

    context = build_qwen_context()
    base = Qwen3ASREngine(WHISPER_MODEL_PRECISE, device=DEVICE, context=context)
    clips = [load_clip(args.meeting, st, args.length) for st in args.starts]
    run(base, clips[0], context)  # 워밍업

    ref = [run(base, c, context) for c in clips]

    t0 = time.perf_counter()
    fast = Qwen3ASREngine(WHISPER_MODEL_PRECISE, device=DEVICE, context=context, fast_decode=True)
    print(f"fast_decode 준비 {time.perf_counter() - t0:.0f}s (로딩+양자화+컴파일 워밍업)")
    print(f"GPU 메모리 할당 {torch.cuda.memory_allocated() / 1e9:.1f}GB\n")

    print(f"{'클립':>6}{'bf16':>9}{'int8':>9}{'속도비':>8}{'글자변화':>9}{'logprob 차':>11}")
    print("-" * 54)
    fast_texts = []
    diffs, speedups = [], []
    for st, c, (ms0, t_ref, lp0) in zip(args.starts, clips, ref):
        ms1, t1, lp1 = run(fast, c, context)
        fast_texts.append(t1)
        d = 100 * edit_ratio(t_ref, t1)
        diffs.append(d)
        speedups.append(ms0 / ms1)
        print(f"{st:>5.0f}s{ms0:>8.0f}ms{ms1:>8.0f}ms{ms0 / ms1:>7.2f}x{d:>8.1f}%{lp1 - lp0:>+11.3f}")
    print(f"{'평균':>6}{'':>18}{sum(speedups) / len(speedups):>7.2f}x{sum(diffs) / len(diffs):>8.1f}%")

    # 재컴파일 정지 시험: 회의마다 달라지는 컨텍스트 길이 × 청크 길이를 섞어 호출하고
    # 유독 오래 걸리는 호출이 있는지 본다(워밍업이 놓친 shape가 있으면 수십 초 걸린다).
    names = ["문지수", "김나연", "이승주", "가동현", "이준오", "홍길동", "김철수"]
    print("\n재컴파일 정지 시험 (컨텍스트 길이 × 청크 길이)")
    slow = []
    for n in (0, 2, 5, 7):
        ctx = build_qwen_context(names[:n]) if n else context
        for sec in (2.0, 4.0, 7.0, 9.0, 13.0, 15.0):
            ms, _t, _lp = run(fast, load_clip(args.meeting, 10.0, sec), ctx)
            if ms > 3000:
                slow.append((n, sec, ms))
    if slow:
        for n, sec, ms in slow:
            print(f"  ⚠️ 이름 {n}명 / {sec:.0f}초 청크: {ms:.0f}ms — 재컴파일 의심")
    else:
        print("  24개 조합 모두 3초 이내 — 재컴파일 정지 없음")

    # 동시 호출: 같은 클립들을 스레드 N개가 동시에 돌려 단독 결과와 비교
    print(f"\n동시 호출 시험 ({args.threads}스레드 × 클립 {len(clips)}개)")
    results: dict[tuple[int, int], str] = {}

    def worker(tid: int):
        for i, c in enumerate(clips):
            results[(tid, i)] = run(fast, c, context)[1]

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(args.threads)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t0
    mismatches = sum(1 for (tid, i), txt in results.items() if txt != fast_texts[i])
    print(f"  전체 {wall:.1f}s, 단독 결과와 다른 호출 {mismatches}/{len(results)}")
    print("  0이어야 한다. 하나라도 있으면 정적 캐시가 스레드 사이에서 겹친 것 — 배포 금지.")


if __name__ == "__main__":
    main()
