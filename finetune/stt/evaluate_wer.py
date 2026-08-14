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


def load_model(model_id: str, adapter_path: str | None = None, itn: bool = True):
    """
    서버와 동일한 기준(아키텍처별 엔진 자동 선택)으로 모델 로딩.

    model_id를 바꿔가며 서로 다른 모델을 같은 평가셋으로 비교할 수 있다
    (예: large-v3 vs large-v3-turbo vs 한국어 파인튜닝된 turbo).

    adapter_path를 주면 LoRA 어댑터를 얹어서 로드 (파인튜닝 전/후 비교용).
    ⚠️ 어댑터는 학습에 쓴 모델과 구조가 같아야 한다 — large-v3로 학습한 어댑터를
    turbo(디코더 레이어 32→4)에 얹으면 로딩 단계에서 실패한다.
    faster-whisper 엔진에서는 어댑터 로딩 자체를 지원하지 않음(peft가 ctranslate2
    포맷을 다루지 않음) — transformers 엔진에서만 의미 있음.

    Qwen3-ASR 계열은 Whisper와 아키텍처가 달라 전용 어댑터로 분기한다.
    (평가 전용 — 서버 파이프라인에는 아직 연결돼 있지 않음)
    """
    if "qwen3-asr" in model_id.lower():
        if adapter_path:
            raise SystemExit("Qwen3-ASR은 LoRA 어댑터 로딩을 지원하지 않음 (평가 전용 어댑터)")
        from qwen_asr_engine import Qwen3ASREngine
        return Qwen3ASREngine(model_id, device=DEVICE, itn=itn)
    # STT_ENGINE이 qwen이어도 Whisper 모델을 비교 대상으로 넘길 수 있어야 한다.
    # 그때 faster-whisper로 빠지면 aarch64에서 GPU를 못 잡고 깨지므로 transformers로 간다.
    if STT_ENGINE in ("transformers", "qwen"):
        from stt.services.whisper_engine import TransformersWhisperEngine
        return TransformersWhisperEngine(model_id, device=DEVICE, adapter_path=adapter_path)
    if adapter_path:
        raise SystemExit("faster-whisper 엔진은 LoRA 어댑터 로딩을 지원하지 않음 (transformers 엔진에서만 가능)")
    from faster_whisper import WhisperModel
    return WhisperModel(model_id, device=DEVICE, compute_type=COMPUTE_TYPE)


# ── AI-Hub 한국어 음성 전사 규약 태그 ──────────────────────────────────────
# 정답 텍스트에 라벨링 기호가 섞여 있는데, 이걸 안 풀면 모델이 정확히 맞혀도
# 오류로 잡혀서 CER이 부풀려진다(held-out 500건 중 231건이 태그 포함).
#
#   (표기형)/(발음형)  이중 전사. 예: (1대16.8)/(일 대 십육 점 팔)
#   n/ o/ b/ l/ u/     잡음·겹침·숨소리·웃음·불명 — 발화가 아니므로 통째로 제거
#   어/ 그/ 뭐/        간투어 — 실제로 말한 내용이므로 단어는 남기고 기호만 제거
#   +                  반복/재시작 발화 마커
#   *                  불명확 발화 마커
#
# 이중 전사는 표기형을 택한다. Whisper 계열이 "1대16.8" 형태로 출력하기 때문에
# 발음형을 정답으로 잡으면 숫자를 맞혀도 전부 오류가 된다 — 숫자 인식이
# 핵심 관심사인 만큼 이 선택이 결과를 크게 좌우한다.
_AIHUB_DUAL = re.compile(r"\(([^()]*)\)\s*/\s*\(([^()]*)\)")
_AIHUB_EVENT = re.compile(r"(?<![가-힣A-Za-z0-9])[bnlou]\s*/")
_AIHUB_FILLER = re.compile(r"([가-힣]+)\s*/")


def strip_aihub_tags(text: str, dual: str = "written") -> str:
    """
    AI-Hub 전사 규약 태그를 실제 발화 텍스트로 되돌린다.

    dual: 이중 전사에서 어느 쪽을 정답으로 볼지.
      "written" — 표기형 "1대16.8". Whisper 계열 출력 형식.
      "spoken"  — 발음형 "일 대 십육 점 팔". Qwen3-ASR은 ITN을 적용하지 않아
                  숫자를 발음형으로 출력하므로, 이쪽으로 맞춰 재측정하면
                  "표기 형식 차이"와 "실제 인식 오류"를 분리할 수 있다.

    두 값의 차이가 곧 후처리(ITN)로 회수 가능한 몫이다.
    """
    text = _AIHUB_DUAL.sub(r"\1" if dual == "written" else r"\2", text)
    text = _AIHUB_EVENT.sub(" ", text)       # 음향 이벤트 태그 제거
    text = _AIHUB_FILLER.sub(r"\1 ", text)   # 간투어는 단어만 남김
    return text.replace("+", " ").replace("*", " ")


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
    # 컨텍스트 바이어싱 텍스트 파일 (용어 목록/배경 설명).
    # ⚠️ Whisper에서는 이 값이 initial_prompt로 들어가는데, 짧은 오디오에서
    #    프롬프트를 그대로 받아적는 문제가 실측으로 확인됐다. Whisper 계열
    #    모델에 이 옵션을 쓸 때는 그 사실을 감안할 것.
    parser.add_argument("--context", default=None, help="컨텍스트 바이어싱 텍스트 파일 경로")
    # 기본값은 raw — 기존 리포트와 그대로 비교할 수 있게 동작을 바꾸지 않는다.
    # AI-Hub 매니페스트를 평가할 때만 aihub를 줘서 태그를 풀고 측정한다.
    # Qwen 계열은 숫자를 발음형으로 출력하므로 기본적으로 후처리(ITN)를 적용한다.
    # 후처리 효과를 분리해서 보려면 --no-itn.
    parser.add_argument("--no-itn", action="store_true", help="한국어 수사→숫자 후처리를 끔 (Qwen 전용)")
    parser.add_argument("--ref-format", choices=["raw", "aihub", "aihub-spoken"], default="raw",
                        help="정답 텍스트 형식. aihub면 태그를 풀고 비교(이중전사=표기형), "
                             "aihub-spoken이면 이중전사를 발음형으로 잡아 ITN 영향을 분리")
    args = parser.parse_args()
    beam_size = args.beam_size if args.beam_size is not None else PRECISE_BEAM_SIZE
    model_id = args.model or WHISPER_MODEL_PRECISE

    with open(args.manifest, encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    stripped = 0
    if args.ref_format.startswith("aihub"):
        dual = "spoken" if args.ref_format == "aihub-spoken" else "written"
        for item in items:
            cleaned = strip_aihub_tags(item["text"], dual=dual)
            if cleaned != item["text"]:
                stripped += 1
            item["text"] = cleaned
        # 태그가 하나도 안 걸리면 형식을 잘못 지정한 것 — 조용히 넘기면
        # 부풀려진 CER을 정상 수치로 착각하게 된다.
        if stripped == 0:
            raise SystemExit(f"❌ --ref-format {args.ref_format}인데 태그가 하나도 안 걸림 — 매니페스트 형식 확인 필요")
        print(f"AI-Hub 태그 정리: {stripped}/{len(items)}건의 정답 텍스트 변경됨")
    terms = []
    if args.terms:
        with open(args.terms, encoding="utf-8") as f:
            # 주석(#)과 빈 줄은 뺀다 — 용어 목록 파일은 선정 근거를 주석으로 달아둔다.
            # (안 거르면 주석 문장 전체가 '용어' 하나로 잡혀 재현율이 0에 수렴한다)
            terms = [s for s in (line.strip() for line in f)
                     if s and not s.startswith("#")]
    context = None
    if args.context:
        with open(args.context, encoding="utf-8") as f:
            # 주석(#)과 빈 줄은 빼고 한 덩어리 텍스트로 만든다
            lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        context = " ".join(lines)

    print(f"엔진={STT_ENGINE}, 모델={model_id}, 어댑터={args.adapter_path or '없음(베이스)'}, "
          f"beam={beam_size}, 컨텍스트={'있음' if context else '없음'}, 평가 대상={len(items)}개")
    model = load_model(model_id, args.adapter_path, itn=not args.no_itn)

    total_word_err = total_words = 0
    total_char_err = total_chars = 0
    total_term_expected = total_term_found = 0
    details = []
    logprobs = []
    started = time.monotonic()

    for i, item in enumerate(items, 1):
        segments, _info = model.transcribe(
            item["audio"],
            language=WHISPER_LANGUAGE,
            beam_size=beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=context,
        )
        segments = list(segments)
        hyp = " ".join(seg.text.strip() for seg in segments).strip()
        # 신뢰도 신호가 실제로 나오는지 확인 (confident 플래그의 근거가 됨)
        seg_logprobs = [s.avg_logprob for s in segments if getattr(s, "avg_logprob", None) is not None]
        item_logprob = sum(seg_logprobs) / len(seg_logprobs) if seg_logprobs else None
        if item_logprob is not None:
            logprobs.append(item_logprob)

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
            "avg_logprob": round(item_logprob, 4) if item_logprob is not None else None,
        })
        print(f"[{i}/{len(items)}] WER={details[-1]['wer']:.2f} CER={details[-1]['cer']:.2f} | {hyp[:50]}")

    report = {
        "engine": STT_ENGINE,
        "model": model_id,
        "adapter": args.adapter_path,
        "beam_size": beam_size,
        "context": args.context,
        "ref_format": args.ref_format,
        "itn": not args.no_itn,
        "num_items": len(items),
        # 건당 평균 처리 시간 — 속도는 타협 불가 기준이라 리포트에 남긴다
        "sec_per_item": round((time.monotonic() - started) / max(len(items), 1), 3),
        "avg_logprob_mean": round(sum(logprobs) / len(logprobs), 4) if logprobs else None,
        "avg_logprob_min": round(min(logprobs), 4) if logprobs else None,
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
    print(f"건당 시간   : {report['sec_per_item']}초")
    print(f"avg_logprob : 평균 {report['avg_logprob_mean']} / 최저 {report['avg_logprob_min']}")
    print(f"리포트 저장 : {args.output}")


if __name__ == "__main__":
    main()
