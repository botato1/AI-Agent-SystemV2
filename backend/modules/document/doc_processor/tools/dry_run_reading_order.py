"""reading_order.py를 실제 파이프라인에 연결하기 전에, 21건 PDF에 대해
'적용했다면 순서가 바뀌었을 블록이 몇 개인지'만 빠르게 미리보기하는 진단 스크립트.

OCR/YOLO를 전혀 돌리지 않고 PyMuPDF 텍스트 추출 + text_cleaner만 거치므로
수 초 안에 21건 전체를 확인할 수 있다.

실행 (backend/modules/document/ 에서):
    python -m doc_processor.tools.dry_run_reading_order <pdf_dir>

특정 문서의 페이지별 전/후 블록 순서를 자세히 보고 싶으면:
    python -m doc_processor.tools.dry_run_reading_order <pdf_dir> --inspect <pdf파일명>

예: python -m doc_processor.tools.dry_run_reading_order test_no_chart
    python -m doc_processor.tools.dry_run_reading_order test_no_chart --inspect 2024011517194575K_02_05_3p.pdf
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

import fitz

from doc_processor.parsers.text_parser import extract_text_blocks
from doc_processor.postprocess import text_cleaner
from doc_processor.postprocess.reading_order import restore_reading_order


def inspect(pdf_dir: str, filename: str) -> None:
    path = Path(pdf_dir) / filename
    doc = fitz.open(str(path))
    for page_index in range(len(doc)):
        page = doc[page_index]
        blocks = extract_text_blocks(page)
        cleaned = text_cleaner.clean_text_blocks(blocks)
        if not cleaned:
            continue
        reordered = restore_reading_order(cleaned)
        before = [b.text for b in cleaned]
        after = [b.text for b in reordered]
        if before == after:
            print(f"\n=== page {page_index + 1}: 변경 없음 ===")
            continue
        print(f"\n=== page {page_index + 1}: BEFORE ===")
        for i, t in enumerate(before):
            print(f"  [{i:3d}] {t[:60]}")
        print(f"=== page {page_index + 1}: AFTER ===")
        for i, t in enumerate(after):
            print(f"  [{i:3d}] {t[:60]}")
    doc.close()


def main(pdf_dir: str) -> None:
    d = Path(pdf_dir)
    # eval_ocr_accuracy.py와 동일한 기준: 정답 .txt가 있는 PDF만 (= 실제 평가 대상 21건)
    pdfs = sorted(p for p in d.glob("*.pdf") if p.with_suffix(".txt").exists())
    if not pdfs:
        print(f"정답 .txt가 매칭되는 PDF 없음: {pdf_dir}")
        return

    print(f"{'문서':40s} {'페이지':>6s} {'블록수':>6s} {'순서변경블록':>10s}")
    print("-" * 70)

    any_changed = False
    for pdf_path in pdfs:
        print(f"{pdf_path.name} ...", end=" ", flush=True)
        try:
            doc = fitz.open(str(pdf_path))
            page_count = len(doc)
            total_blocks = 0
            total_changed = 0
            changed_pages = []
            for page_index in range(page_count):
                page = doc[page_index]
                blocks = extract_text_blocks(page)
                cleaned = text_cleaner.clean_text_blocks(blocks)
                if not cleaned:
                    continue
                reordered = restore_reading_order(cleaned)

                before = [b.text for b in cleaned]
                after = [b.text for b in reordered]
                # 단순 위치별(zip) 비교는 블록 하나만 옮겨도 그 뒤 전부가
                # "변경"으로 잡히는 착시가 생긴다 (쪽번호 하나가 맨 뒤로
                # 이동하면 나머지 전부 인덱스가 밀림). 실제로 내용이 이동한
                # 블록 수만 세려면 매칭되지 않는 부분만 계산해야 한다.
                matcher = difflib.SequenceMatcher(None, before, after)
                matched = sum(block.size for block in matcher.get_matching_blocks())
                changed = len(before) - matched
                total_blocks += len(cleaned)
                if changed:
                    total_changed += changed
                    changed_pages.append(page_index + 1)
            doc.close()
        except Exception as e:
            print(f"\r{pdf_path.name:40s} ERROR: {e}")
            continue

        marker = ""
        if total_changed:
            any_changed = True
            marker = f"  <- 페이지 {changed_pages}"
        print(
            f"\r{pdf_path.name:40s} {page_count:>6d} {total_blocks:>6d} "
            f"{total_changed:>10d}{marker}"
        )

    print("-" * 70)
    if not any_changed:
        print("영향받은 문서 없음 — 새 로직이 어떤 문서에도 순서를 바꾸지 않았습니다.")
    else:
        print("위에 표시된 문서만 순서가 바뀝니다. 해당 문서를 직접 열어 실제로")
        print("올바른 순서인지 확인한 뒤 파이프라인에 연결하세요.")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[2] == "--inspect":
        inspect(sys.argv[1], sys.argv[3])
    elif len(sys.argv) == 2:
        main(sys.argv[1])
    else:
        print("사용법: python -m doc_processor.tools.dry_run_reading_order <pdf_dir>")
        print("       python -m doc_processor.tools.dry_run_reading_order <pdf_dir> --inspect <파일명>")
        sys.exit(1)
