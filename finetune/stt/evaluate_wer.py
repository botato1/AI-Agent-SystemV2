"""
STT 성능 평가 스크립트 — WER / CER / 용어 재현율 측정.

파인튜닝 전(베이스라인)과 후에 같은 매니페스트로 실행해서 두 리포트를 비교한다.
지표 정의:
  - WER: 단어(어절) 단위 오류율. 낮을수록 좋음.
  - CER: 글자 단위 오류율. 한국어는 띄어쓰기 오류에 덜 민감한 CER도 같이 봐야 함.
  - 용어 재현율: terms.txt의 핵심 용어가 정답에 등장한 횟수 대비 인식 결과에도
    등장한 비율. 파인튜닝의 핵심 목표 지표. (띄어쓰기 오류에 강건하도록
    공백 제거 후 부분 문자열 매칭)

사용법 (GPU 서버, stt venv 활성화 후):
  python evaluate_wer.py --manifest manifest.jsonl --terms terms.txt --output baseline_report.json

서버 실행 규약(uvicorn stt.main:app, cwd=backend/modules)과 동일한 방식으로
stt 패키지를 임포트하므로, 엔진(faster-whisper/transformers)은 서버와 동일하게
자동 선택된다.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata

# 리포 루트 기준 backend/modules를 import 경로에 추가 (서버 실행 규약과 동일)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import (  # noqa: E402
    STT_ENGINE, DEVICE, COMPUTE_TYPE,
    WHISPER_MODEL_PRECISE, WHISPER_LANGUAGE, PRECISE_BEAM_SIZE,
)


def load_model(model_id: str, adapter_path: str | None = None):
    """
    서버와 동일한 기준(아키텍처별 엔진 자동 선택)으로 모델 로딩.

    model_id를 바꿔가며 서로 다른 모델을 같은 평가셋으로 비교할 수 있다
    (예: large-v3 vs large-v3-turbo vs 한국어 파인튜닝된 turbo).

    adapter_path를 주면 LoRA 어댑터를 얹어서 로드 (파인튜닝 전/후 비교용).
    ⚠️ 어댑터는 학습에 쓴 모델과 구조가 같아야 한다 — large-v3로 학습한 어댑터를
    turbo(디코더 레이어 32→4)에 얹으면 로딩 단계에서 실패한다.
    faster-whisper 엔진에서는 어댑터 로딩 자체를 지원하지 않음(peft가 ctranslate2
    포맷을 다루지 않음) — transformers 엔진에서만 의미 있음.
    """
    if STT_ENGINE == "transformers":
        from stt.services.whisper_engine import TransformersWhisperEngine
        return TransformersWhisperEngine(model_id, device=DEVICE, adapter_path=adapter_path)
    if adapter_path:
        raise SystemExit("faster-whisper 엔진은 LoRA 어댑터 로딩을 지원하지 않음 (transformers 엔진에서만 가능)")
    from faster_whisper import WhisperModel
    return WhisperModel(model_id, device=DEVICE, compute_type=COMPUTE_TYPE)


def normalize(text: str) -> str:
    """비교 전 정규화: 유니코드 정규화, 소문자화, 문장부호 제거, 공백 정리."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def edit_distance(ref: list, hyp: list) -> int:
    """표준 편집 거리 (삽입/삭제/치환)."""
    dp = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, len(hyp) + 1):
            cur = dp[j]
            dp[j] = min(
                dp[j] + 1,          # 삭제
                dp[j - 1] + 1,      # 삽입
                prev + (ref[i - 1] != hyp[j - 1]),  # 치환
            )
            prev = cur
    return dp[-1]


def term_stats(ref_norm: str, hyp_norm: str, terms: list[str]) -> tuple[int, int]:
    """(정답에 등장한 용어 총 횟수, 그중 인식 결과에도 있는 횟수)."""
    ref_compact = ref_norm.replace(" ", "")
    hyp_compact = hyp_norm.replace(" ", "")
    expected = found = 0
    for term in terms:
        t = normalize(term).replace(" ", "")
        count_ref = ref_compact.count(t)
        if count_ref == 0:
            continue
        expected += count_ref
        found += min(count_ref, hyp_compact.count(t))
    return expected, found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="jsonl: {\"audio\": ..., \"text\": ...}")
    parser.add_argument("--terms", default=None, help="용어 재현율 평가용 용어 목록 파일")
    parser.add_argument("--output", default="report.json")
    parser.add_argument("--adapter-path", default=None, help="LoRA 어댑터 경로 (없으면 순정 베이스 모델)")
    # beam 크기는 정확도/속도 트레이드오프의 가장 큰 레버라 실측 비교가 필요함.
    # 미지정 시 서버 설정(PRECISE_BEAM_SIZE)을 그대로 써서 기존 동작과 동일.
    parser.add_argument("--beam-size", type=int, default=None, help=f"빔 크기 (미지정 시 서버 설정값 {PRECISE_BEAM_SIZE})")
    # 모델을 바꿔가며 같은 평가셋으로 비교하기 위한 옵션 (예: turbo 계열, 한국어 파인튜닝 모델)
    parser.add_argument("--model", default=None, help=f"모델 ID (미지정 시 서버 설정값 {WHISPER_MODEL_PRECISE})")
    args = parser.parse_args()
    beam_size = args.beam_size if args.beam_size is not None else PRECISE_BEAM_SIZE
    model_id = args.model or WHISPER_MODEL_PRECISE

    with open(args.manifest, encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    terms = []
    if args.terms:
        with open(args.terms, encoding="utf-8") as f:
            terms = [line.strip() for line in f if line.strip()]

    print(f"엔진={STT_ENGINE}, 모델={model_id}, 어댑터={args.adapter_path or '없음(베이스)'}, "
          f"beam={beam_size}, 평가 대상={len(items)}개")
    model = load_model(model_id, args.adapter_path)

    total_word_err = total_words = 0
    total_char_err = total_chars = 0
    total_term_expected = total_term_found = 0
    details = []
    started = time.monotonic()

    for i, item in enumerate(items, 1):
        segments, _info = model.transcribe(
            item["audio"],
            language=WHISPER_LANGUAGE,
            beam_size=beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        hyp = " ".join(seg.text.strip() for seg in segments).strip()

        ref_norm, hyp_norm = normalize(item["text"]), normalize(hyp)
        ref_words, hyp_words = ref_norm.split(), hyp_norm.split()
        ref_chars, hyp_chars = list(ref_norm.replace(" ", "")), list(hyp_norm.replace(" ", ""))

        word_err = edit_distance(ref_words, hyp_words)
        char_err = edit_distance(ref_chars, hyp_chars)
        expected, found = term_stats(ref_norm, hyp_norm, terms)

        total_word_err += word_err
        total_words += len(ref_words)
        total_char_err += char_err
        total_chars += len(ref_chars)
        total_term_expected += expected
        total_term_found += found

        details.append({
            "audio": item["audio"],
            "reference": item["text"],
            "hypothesis": hyp,
            "wer": round(word_err / max(len(ref_words), 1), 4),
            "cer": round(char_err / max(len(ref_chars), 1), 4),
            "terms_expected": expected,
            "terms_found": found,
        })
        print(f"[{i}/{len(items)}] WER={details[-1]['wer']:.2f} CER={details[-1]['cer']:.2f} | {hyp[:50]}")

    report = {
        "engine": STT_ENGINE,
        "model": model_id,
        "adapter": args.adapter_path,
        "beam_size": beam_size,
        "num_items": len(items),
        "wer": round(total_word_err / max(total_words, 1), 4),
        "cer": round(total_char_err / max(total_chars, 1), 4),
        "term_recall": round(total_term_found / max(total_term_expected, 1), 4) if total_term_expected else None,
        "term_expected_total": total_term_expected,
        "term_found_total": total_term_found,
        "elapsed_sec": round(time.monotonic() - started, 1),
        "details": details,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n===== 종합 =====")
    print(f"WER        : {report['wer']:.4f}")
    print(f"CER        : {report['cer']:.4f}")
    print(f"용어 재현율 : {report['term_recall']}")
    print(f"리포트 저장 : {args.output}")


if __name__ == "__main__":
    main()
