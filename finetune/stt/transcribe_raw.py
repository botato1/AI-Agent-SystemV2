"""
회의 오디오를 **우리 턴 로직을 전혀 거치지 않고** 통째로 전사한다.

왜 필요한가:
  전사가 나쁠 때 원인은 둘 중 하나다.
    ① 오디오 자체가 어렵다(발음, 거리, 울림, 겹침) — 모델이 못 알아듣는다
    ② 우리가 오디오를 잘못 잘라 넘긴다 — 모델은 멀쩡한데 입력이 망가졌다

  재분석은 화자분리 턴을 겹침 기준으로 정리하고 화자 경계로 다시 쪼갠 뒤 전사한다.
  그 과정에서 문장이 중간에서 잘리면 전사가 나빠진다("전사 단위를 바꾸면 전사 결과가
  바뀐다"는 것은 2026-08-04에 실측됐다 — 그때는 단어 하나 차이였지만, 오디오가
  어려워지면 그 대가가 커질 수 있다).

  이 스크립트는 **자르지 않고** 넘긴다. 그 결과가
    - 좋으면  → 우리 자르기가 범인이다(②)
    - 나쁘면  → 오디오가 어렵다(①). 자르기를 아무리 고쳐도 안 된다.

  원인을 가르지 않고 고치기 시작하면 엉뚱한 데를 파게 된다.

사용법:
  python transcribe_raw.py --meeting <회의ID> --script <대본파일>
  python transcribe_raw.py --meeting <회의ID> --no-context   (용어 힌트 없이)
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, WHISPER_LANGUAGE, PRECISE_BEAM_SIZE, WHISPER_MODEL_PRECISE,
    build_context_hint,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--script", default=None, help="정답 대본 (주면 CER까지 낸다)")
    parser.add_argument("--no-context", action="store_true",
                        help="용어 힌트 없이 전사. 힌트가 오히려 해가 되는지 확인용")
    args = parser.parse_args()

    meeting_dir = os.path.join(MEETINGS_DIR, args.meeting)
    audio, sample_rate = sf.read(os.path.join(meeting_dir, args.audio), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    print(f"오디오 {len(audio) / sample_rate:.1f}초 / 모델 {WHISPER_MODEL_PRECISE}")

    # 앱과 같은 방식으로 모델을 만든다 — 다른 설정으로 재면 비교가 무의미하다
    from stt.main import _load_whisper_model
    prompt = None if args.no_context else build_context_hint(None)
    print(f"용어 힌트 {'없음' if args.no_context else '적용'}\n")
    model = _load_whisper_model(WHISPER_MODEL_PRECISE, with_context=not args.no_context)

    segments, _info = model.transcribe(
        audio,
        language=WHISPER_LANGUAGE,
        beam_size=PRECISE_BEAM_SIZE,
        vad_filter=True,
        initial_prompt=prompt,
        condition_on_previous_text=False,
    )
    segments = list(segments)

    print("=" * 78)
    for seg in segments:
        print(f"[{seg.start:6.1f}~{seg.end:6.1f}] {seg.text.strip()}")
    print("=" * 78)

    hypothesis = " ".join(s.text.strip() for s in segments)
    if not args.script:
        print("\n(--script로 대본을 주면 CER을 낸다)")
        return

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from evaluate_against_script import cer, load_script
    script = load_script(os.path.expanduser(args.script))
    reference = " ".join(line["text"] for line in script)
    errors, total = cer(reference, hypothesis)
    print(f"\nCER(자르지 않고 통째로 전사): {errors / max(total,1) * 100:.2f}%  "
          f"({errors}자 오류 / 정답 {total}자)")
    print("\n비교 대상:")
    print("  evaluate_against_script.py로 잰 재분석본 CER과 견줄 것.")
    print("  이쪽이 확실히 낮으면 → 우리가 오디오를 잘못 잘라 넘기고 있다.")
    print("  비슷하거나 더 높으면 → 오디오 자체가 어렵다. 자르기를 고쳐도 안 된다.")


if __name__ == "__main__":
    main()
