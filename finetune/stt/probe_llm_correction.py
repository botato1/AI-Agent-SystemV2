"""
LLM 문맥 교정이 실제로 도움이 되는지 잰다.

왜 그냥 켜면 안 되는가:
  이 기능의 가장 큰 위험은 **멀쩡한 문장을 LLM이 고쳐버리는 것**이다. 전사가 조금
  틀린 것보다 내용이 바뀌는 쪽이 훨씬 나쁘다 — 모순 감지가 없던 모순을 만들어낼 수 있다.
  "몇 개 고쳤다"는 숫자만 보면 그게 개선인지 훼손인지 알 수 없다.

  그래서 **무엇을 어떻게 고쳤는지 전부 눈으로 보고** 판단한다.

정답 대본이 있으면 --truth로 주면 교정 전후 CER까지 나온다. 없으면 변경 목록만 본다
(그것만으로도 "말투를 다듬었다", "내용을 요약했다" 같은 사고는 바로 보인다).

사용법:
  python probe_llm_correction.py --meeting <회의ID>
  python probe_llm_correction.py --meeting <회의ID> --truth script.txt
"""
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    MEETINGS_DIR, REFINE_LLM_MODEL, REFINE_LLM_URL, REFINE_LLM_MAX_EDIT_RATIO,
    build_context_hint,
)
import stt.core.config as config  # noqa: E402
from stt.services.transcript_correction import correct_transcript  # noqa: E402


def cer(reference: str, hypothesis: str) -> float:
    """글자 단위 오류율 — 한국어는 어절 경계가 모호해서 WER 대신 CER을 쓴다."""
    ref = "".join(reference.split())
    hyp = "".join(hypothesis.split())
    if not ref:
        return 0.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(
                previous[j] + 1, current[j - 1] + 1,
                previous[j - 1] + (r != h),
            ))
        previous = current
    return previous[-1] / len(ref)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--truth", default=None, help="정답 대본 텍스트 파일 (선택)")
    args = parser.parse_args()

    # 서버 환경변수와 무관하게 이 실험에서는 켠다 — 끄고 재는 건 의미가 없다
    config.REFINE_LLM_ENABLED = True
    import stt.services.transcript_correction as tc
    tc.REFINE_LLM_ENABLED = True

    meta_path = os.path.join(MEETINGS_DIR, args.meeting, "transcript.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    segments = meta.get("segments") or []
    if not segments:
        raise SystemExit("❌ 세그먼트가 없다 — 재분석을 먼저 돌릴 것")

    before = [seg["text"] for seg in segments]
    print(f"LLM   : {REFINE_LLM_MODEL} @ {REFINE_LLM_URL}")
    print(f"변경 한도: 글자 {REFINE_LLM_MAX_EDIT_RATIO:.0%}")
    print(f"세그먼트 {len(segments)}개\n")

    changed = correct_transcript(segments, build_context_hint(None, meta.get("session_id")))

    print(f"\n{'=' * 70}")
    if not changed:
        print("고친 것 없음.")
        print("  — 오인식이 실제로 없었거나, LLM이 못 잡았거나, 안전장치가 전부 거부했거나.")
        print("  — 서버 로그의 '교정 거부' 줄을 보면 어느 쪽인지 구분된다.")
    else:
        print(f"고친 줄 {changed}개 — **하나하나 확인할 것**")
        print(f"{'=' * 70}")
        for i, seg in enumerate(segments):
            if seg.get("llm_corrected"):
                print(f"\n[{seg['start']:.1f}s]")
                print(f"  전: {before[i]}")
                print(f"  후: {seg['text']}")

    if args.truth:
        with open(os.path.expanduser(args.truth), encoding="utf-8") as f:
            # 대본에서 "이름: 발화" 형태의 화자 표기를 떼어낸다
            reference = " ".join(
                line.split(":", 1)[-1].strip()
                for line in f if line.strip()
            )
        cer_before = cer(reference, " ".join(before))
        cer_after = cer(reference, " ".join(seg["text"] for seg in segments))
        print(f"\n{'=' * 70}")
        print(f"CER 교정 전 {cer_before:.2%} → 교정 후 {cer_after:.2%} "
              f"({'개선' if cer_after < cer_before else '악화'} "
              f"{abs(cer_after - cer_before) * 100:.2f}%p)")
        print("\n⚠️ CER이 좋아져도 변경 목록을 직접 볼 것 — 내용이 바뀌는 사고는")
        print("   글자 수로는 잘 안 드러난다.")

    print("\n(이 스크립트는 파일을 저장하지 않는다 — 실제 회의록은 그대로다)")


if __name__ == "__main__":
    main()
