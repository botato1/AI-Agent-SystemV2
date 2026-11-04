"""
int8 + 정적 캐시/compile 엔진(fast_decode)이 **서버에서만 느린 이유**를 가린다.

왜 필요한가 (2026-11-04, NEXT.md 10번):
  probe_engine_int8.py에서는 12초 클립이 0.64~0.99초였는데(bf16의 약 2배 빠름), 실제 서버
  스윕(`sweep_chunk_cap.py --int8`)에서는 15초 청크가 8~10초 걸렸다(평균 지연 6.60초,
  bf16은 1.77초). 워밍업 로그는 정상(호출당 0.3~0.4초)이었고 컴파일 경고도 없었다.
  단독 점검과 서버의 차이는 "호출하는 스레드"와 "다른 GPU 작업과의 경쟁"이다.
  CUDA 그래프(reduce-overhead)는 스레드마다 따로 기록되므로, 워밍업을 한 스레드와 다른
  실행기(executor) 스레드에서 부르면 매번 다시 캡처할 수 있다는 가설을 시험한다.

같은 엔진·같은 클립·같은 컨텍스트로 호출 환경만 바꿔 호출당 시간을 잰다:
  A  메인 스레드                  — 기준(단독 점검과 같은 조건)
  B  호출마다 새 스레드            — 실행기 스레드가 매번 바뀌는 최악의 경우
  C  전용 스레드 하나(max_workers=1) — 해결책 후보: 모든 호출이 같은 스레드
  D  다른 GPU 작업을 동시에 돌리며 메인 스레드 — 경쟁 조건

해석:
  B만 느리고 C가 A와 같으면 → 스레드별 그래프 캡처가 원인. 전용 스레드로 가면 해결.
  A·B·C가 모두 빠르고 D만 느리면 → GPU 경쟁이 원인.
  전부 빠르면 → 스윕 당시 서버 환경(다른 프로세스 등)의 문제, 코드 문제가 아님.

서버를 띄워둔 채 별도 프로세스로 모델을 올린다(GB10 128GB 통합). 회의가 없을 때 돌릴 것.

사용법 (GPU 서버, stt venv; torchao 필요):
  python probe_engine_threads.py
"""
import argparse
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from profile_precise_pass import DEFAULT_MEETING, load_clip  # noqa: E402
from stt.core.config import DEVICE, WHISPER_MODEL_PRECISE, WHISPER_MODEL_FAST, build_qwen_context  # noqa: E402
from stt.services.qwen_engine import Qwen3ASREngine  # noqa: E402


def call(engine, clip, context) -> float:
    t0 = time.perf_counter()
    engine.transcribe(clip, language="ko", beam_size=1, vad_filter=True, initial_prompt=context)
    return time.perf_counter() - t0


def summarize(label: str, times: list[float]) -> None:
    print(f"{label:<34}평균 {statistics.mean(times):5.2f}s  중앙 {statistics.median(times):5.2f}s  "
          f"최대 {max(times):5.2f}s   {' '.join(f'{t:.1f}' for t in times)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", default=DEFAULT_MEETING)
    ap.add_argument("--length", type=float, default=15.0)
    ap.add_argument("--n", type=int, default=8)
    args = ap.parse_args()

    names = ["문지수", "김나연", "이승주", "이준오"]  # 스윕의 ba8 회의와 같은 4명
    context = build_qwen_context(names)
    clip = load_clip(args.meeting, 5.0, args.length)

    print(f"int8 엔진 준비 중 (로딩 + 양자화 + 컴파일 워밍업, 수 분)...")
    engine = Qwen3ASREngine(WHISPER_MODEL_PRECISE, device=DEVICE, context=context, fast_decode=True)
    print(f"GPU 메모리 {torch.cuda.memory_allocated() / 1e9:.1f}GB\n")

    call(engine, clip, context)  # 메인 스레드 워밍업 한 번

    # A. 메인 스레드
    summarize("A 메인 스레드", [call(engine, clip, context) for _ in range(args.n)])

    # B. 호출마다 새 스레드
    times_b: list[float] = []

    def run_new_thread():
        out = []
        th = threading.Thread(target=lambda: out.append(call(engine, clip, context)))
        th.start()
        th.join()
        return out[0]

    summarize("B 호출마다 새 스레드", [run_new_thread() for _ in range(args.n)])

    # C. 전용 스레드 하나 — 워밍업 2회는 같은 스레드에서(그래프 재기록 비용을 빼기 위해)
    with ThreadPoolExecutor(max_workers=1) as pool:
        for _ in range(2):
            pool.submit(call, engine, clip, context).result()
        summarize("C 전용 스레드 하나", [pool.submit(call, engine, clip, context).result()
                                      for _ in range(args.n)])

    # D. 다른 GPU 작업(빠른 0.6B 모델 연속 전사)을 백그라운드로 돌리며 메인 스레드
    print("\n경쟁 조건 시험용 0.6B 모델 로딩...")
    fast = Qwen3ASREngine(WHISPER_MODEL_FAST, device=DEVICE, context=None)
    stop = threading.Event()

    def background():
        while not stop.is_set():
            fast.transcribe(clip, language="ko", beam_size=1, vad_filter=True)

    bg = threading.Thread(target=background, daemon=True)
    bg.start()
    time.sleep(2)
    summarize("D 백그라운드 0.6B와 동시", [call(engine, clip, context) for _ in range(args.n)])
    stop.set()
    bg.join(timeout=30)

    print("\n읽는 법")
    print("  B만 느리고 C가 A와 비슷하면 스레드별 그래프 캡처 → 전용 스레드로 해결.")
    print("  D만 느리면 GPU 경쟁. 모두 빠르면 스윕 당시 서버 환경 문제.")


if __name__ == "__main__":
    main()
