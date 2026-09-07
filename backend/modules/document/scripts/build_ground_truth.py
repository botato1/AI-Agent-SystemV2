"""eval_subset의 PDF들을 실제 평가에 쓸 수 있는 형태로 다듬고 정답(.txt)을 자동 생성한다.

하는 일 두 가지:
    1. 페이지 수가 너무 많은 문서(수백 페이지짜리 회의록 등)를 대표 페이지
       몇 장만 남기도록 트리밍한다. 안 그러면 문서 하나 처리하는 데만도
       너무 오래 걸려서 60건을 다 테스트하기 현실적으로 어렵다.
    2. 트리밍된(또는 원래 짧은) 페이지들의 텍스트 레이어를 PyMuPDF로 그대로
       추출해 정답(.txt)으로 저장한다 — 디지털 PDF라 사람이 옮겨 적을 필요가 없다.
    추가로 scanned_photo의 jpg는 파이프라인이 fitz+pdfplumber로 "진짜 PDF"를
    기대하므로, 1페이지짜리 PDF로 감싸서 함께 평가 가능하게 만든다.

주의: storage/test_data/{dart_reports,assembly_minutes}의 원본은 건드리지 않고,
      eval_subset 안의 복사본만 트리밍한다.

사용법:
    python backend/modules/document/scripts/build_ground_truth.py --max-pages 6
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz  # PyMuPDF

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[4] / "storage" / "test_data" / "eval_subset"
MIN_TEXT_LEN = 100  # 이보다 텍스트가 적은 페이지(표지/여백)는 대표 페이지에서 제외


def _pick_representative_pages(doc: fitz.Document, max_pages: int) -> list[int]:
    n = len(doc)
    if n <= max_pages:
        return list(range(n))

    # 내용이 있는 페이지만 후보로 삼되, 없으면 전체를 후보로 둔다.
    candidates = [i for i in range(n) if len(doc[i].get_text().strip()) >= MIN_TEXT_LEN]
    if len(candidates) < max_pages:
        candidates = list(range(n))

    # 문서 전반에 고르게 퍼지도록 등간격으로 선택 (초반/중반/후반 내용이 섞이게)
    step = len(candidates) / max_pages
    picked = sorted({candidates[int(i * step)] for i in range(max_pages)})

    # 중복 제거로 개수가 모자라면 뒤에서 채운다.
    i = len(candidates) - 1
    while len(picked) < max_pages and i >= 0:
        picked_set = set(picked)
        if candidates[i] not in picked_set:
            picked.append(candidates[i])
            picked = sorted(set(picked))
        i -= 1

    return picked[:max_pages]


def trim_and_extract(pdf_path: Path, max_pages: int) -> None:
    doc = fitz.open(pdf_path)
    original_pages = len(doc)

    indices = _pick_representative_pages(doc, max_pages)
    text = "\n".join(doc[i].get_text() for i in indices)

    if len(indices) < original_pages:
        doc.select(indices)
        doc.save(str(pdf_path) + ".tmp", garbage=4, deflate=True)
        doc.close()
        Path(str(pdf_path) + ".tmp").replace(pdf_path)
        print(f"  [트리밍] {pdf_path.name}: {original_pages}p → {len(indices)}p")
    else:
        doc.close()
        print(f"  [유지] {pdf_path.name}: {original_pages}p (그대로)")

    txt_path = pdf_path.with_suffix(".txt")
    txt_path.write_text(text, encoding="utf-8")


def wrap_images_as_pdf(image_dir: Path) -> None:
    """scanned_photo의 jpg를 1페이지 PDF로 감싼다 (파이프라인이 PDF만 읽으므로)."""
    from PIL import Image

    for jpg_path in sorted(image_dir.glob("*.jpg")):
        pdf_path = jpg_path.with_suffix(".pdf")
        if pdf_path.exists():
            continue
        img = Image.open(jpg_path).convert("RGB")
        img.save(pdf_path, "PDF", resolution=100.0)
        print(f"  [PDF변환] {jpg_path.name} → {pdf_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pages", type=int, default=6, help="문서당 남길 최대 대표 페이지 수")
    args = parser.parse_args()

    print(f"[1/2] dart / assembly 문서 트리밍 + 정답(.txt) 생성 (최대 {args.max_pages}페이지)...")
    for sub in ("dart", "assembly"):
        sub_dir = BASE_DIR / sub
        for pdf_path in sorted(sub_dir.glob("*.pdf")):
            trim_and_extract(pdf_path, args.max_pages)

    print("\n[2/2] scanned_photo jpg → 1페이지 PDF 변환...")
    wrap_images_as_pdf(BASE_DIR / "scanned_photo")

    print("\n완료 — eval_ocr_accuracy.py로 바로 평가 가능한 상태입니다.")


if __name__ == "__main__":
    main()
