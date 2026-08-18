"""OCR 문서 정확도 자체 평가 스크립트.

사용법:
    python eval_ocr_accuracy.py <test_dir>

<test_dir> 구조 (PDF와 정답 텍스트를 같은 이름으로 매칭):
    test_dir/
      slide01.pdf
      slide01.txt   <- slide01.pdf의 정답(ground truth) 전체 텍스트
      slide02.pdf
      slide02.txt
      ...

정답 텍스트(.txt)는 해당 PDF/PPT를 사람이 직접 보고 옮겨 적은 텍스트입니다.
표/이미지 안 글자까지 포함해서 최대한 그대로 옮겨 적어야 정확도가 의미를 가집니다.

출력:
  - 문서별 CER(문자 오류율) / WER(단어 오류율) / 정확도(%)
  - 전체 평균 + OcrStats 요약(성공률, useful 비율 등)
  - 결과를 <test_dir>/eval_report.json 으로 저장
"""
from __future__ import annotations

import json
import os
import site
import sys
from pathlib import Path

# paddlepaddle-gpu의 CUDA DLL 경로 등록 (Windows에서만 필요)
if os.name == "nt":
    import glob
    for _sp in site.getsitepackages():
        for _d in glob.glob(os.path.join(_sp, "nvidia", "*", "bin")):
            os.add_dll_directory(_d)

from doc_processor.core.pipeline import DocumentPipeline


def _normalize(text: str) -> str:
    """공백/줄바꿈 차이를 무시하도록 정규화."""
    return " ".join(text.split())


def _levenshtein(a: list, b: list) -> int:
    """두 시퀀스 간 편집 거리 (삽입/삭제/치환 각각 비용 1)."""
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        ai = a[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ai == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,        # 삭제
                curr[j - 1] + 1,    # 삽입
                prev[j - 1] + cost, # 치환/일치
            )
        prev = curr
    return prev[m]


def compute_cer(pred: str, gt: str) -> float:
    """문자 오류율(Character Error Rate). gt가 빈 문자열이면 0.0."""
    pred_n, gt_n = _normalize(pred), _normalize(gt)
    if not gt_n:
        return 0.0
    dist = _levenshtein(list(pred_n), list(gt_n))
    return dist / len(gt_n)


def compute_wer(pred: str, gt: str) -> float:
    """단어 오류율(Word Error Rate). gt가 빈 문자열이면 0.0."""
    pred_words, gt_words = _normalize(pred).split(), _normalize(gt).split()
    if not gt_words:
        return 0.0
    dist = _levenshtein(pred_words, gt_words)
    return dist / len(gt_words)


def extract_all_text(doc_result) -> str:
    """DocumentResult에서 텍스트/표/이미지OCR/차트 텍스트를 모두 이어붙입니다."""
    parts: list[str] = []
    for page in doc_result.pages:
        c = page.content
        parts.extend(tb.text for tb in c.text)
        parts.extend(tb.markdown for tb in c.tables)
        parts.extend(ib.ocr_text for ib in c.images)
        parts.extend(cb.description for cb in c.charts)
    return "\n".join(parts)


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: python eval_ocr_accuracy.py <test_dir>")
        sys.exit(1)

    test_dir = Path(sys.argv[1])
    pdf_files = sorted(test_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[에러] {test_dir} 안에 .pdf 파일이 없습니다.")
        sys.exit(1)

    pipeline = DocumentPipeline()
    results = []
    total_dist_char = total_len_char = 0
    total_dist_word = total_len_word = 0

    for pdf_path in pdf_files:
        gt_path = pdf_path.with_suffix(".txt")
        if not gt_path.exists():
            print(f"[스킵] 정답 파일 없음: {gt_path.name}")
            continue

        print(f"\n{'='*60}\n처리 중: {pdf_path.name}\n{'='*60}")
        doc_result = pipeline.run(str(pdf_path))
        pred_text = extract_all_text(doc_result)
        gt_text = gt_path.read_text(encoding="utf-8")

        cer = compute_cer(pred_text, gt_text)
        wer = compute_wer(pred_text, gt_text)

        gt_n = _normalize(gt_text)
        pred_n = _normalize(pred_text)
        dist_c = _levenshtein(list(pred_n), list(gt_n))
        dist_w = _levenshtein(pred_n.split(), gt_n.split())
        total_dist_char += dist_c
        total_len_char += max(len(gt_n), 1)
        total_dist_word += dist_w
        total_len_word += max(len(gt_n.split()), 1)

        results.append({
            "file": pdf_path.name,
            "cer": round(cer, 4),
            "wer": round(wer, 4),
            "accuracy_char_pct": round((1 - cer) * 100, 2),
            "accuracy_word_pct": round((1 - wer) * 100, 2),
            "gt_chars": len(gt_n),
            "pred_chars": len(pred_n),
            "ocr_success_ratio": doc_result.ocr_stats.success_ratio,
            "ocr_useful_ratio": doc_result.ocr_stats.useful_ratio,
            "avg_quality_score": doc_result.ocr_stats.avg_quality_score,
            "processing_time_sec": doc_result.ocr_stats.processing_time_sec,
        })

        print(f"  CER={cer*100:.2f}%  WER={wer*100:.2f}%  "
              f"글자정확도={((1-cer)*100):.2f}%  단어정확도={((1-wer)*100):.2f}%")

    if not results:
        print("[에러] 평가할 문서가 없습니다 (정답 .txt가 매칭되는 .pdf가 없음).")
        sys.exit(1)

    overall_cer = total_dist_char / total_len_char
    overall_wer = total_dist_word / total_len_word

    print(f"\n{'='*60}\n전체 결과 ({len(results)}건)\n{'='*60}")
    print(f"  전체 CER          : {overall_cer*100:.2f}%")
    print(f"  전체 WER          : {overall_wer*100:.2f}%")
    print(f"  전체 글자 정확도  : {(1-overall_cer)*100:.2f}%")
    print(f"  전체 단어 정확도  : {(1-overall_wer)*100:.2f}%")

    report = {
        "documents": results,
        "overall": {
            "cer": round(overall_cer, 4),
            "wer": round(overall_wer, 4),
            "accuracy_char_pct": round((1 - overall_cer) * 100, 2),
            "accuracy_word_pct": round((1 - overall_wer) * 100, 2),
            "doc_count": len(results),
        },
    }
    out_path = test_dir / "eval_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n리포트 저장: {out_path}")


if __name__ == "__main__":
    main()
