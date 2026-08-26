"""Figure 이미지 데이터 수집 스크립트.

PDF를 돌리면서 YOLO가 감지한 figure(표/차트) 이미지를 크롭해서 저장합니다.
저장된 이미지를 수동으로 chart / table_image 폴더로 분류하면 학습 데이터 완성.

사용법:
    python collect_figures.py --input ./pdfs --output ./dataset/raw

출력 구조:
    dataset/raw/
        doc1_page1_fig0.jpg
        doc1_page1_fig1.jpg
        ...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz
from PIL import Image

from doc_processor.parsers.yolo_layout_parser import get_parser as get_yolo
from doc_processor.parsers.image_parser import crop_layout_rect, is_valid_crop


def collect(pdf_path: Path, output_dir: Path) -> int:
    yolo = get_yolo()
    layout = yolo.parse(str(pdf_path))
    if not layout:
        print(f"  [SKIP] YOLO 결과 없음: {pdf_path.name}")
        return 0

    doc = fitz.open(str(pdf_path))
    saved = 0

    for page_no, blocks in layout.items():
        figures = [b for b in blocks if b.type == "figure" and not b.ocr_skip]
        if not figures:
            continue

        fitz_page = doc[page_no - 1]
        dpi = 220
        pix = fitz_page.get_pixmap(dpi=dpi, alpha=False)
        page_img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        for i, block in enumerate(figures):
            cropped = crop_layout_rect(page_img, block.bbox, dpi=dpi)
            if not is_valid_crop(cropped):
                continue

            stem = pdf_path.stem.replace(" ", "_")[:30]
            fname = f"{stem}_p{page_no}_f{i}_yolo{block.figure_type}.jpg"
            out_path = output_dir / fname
            cropped.save(out_path, "JPEG", quality=95)
            print(f"  저장: {fname} ({block.figure_type})")
            saved += 1

    doc.close()
    return saved


def main():
    parser = argparse.ArgumentParser(description="Figure 이미지 데이터 수집")
    parser.add_argument("--input", required=True, help="PDF 폴더 또는 단일 PDF 경로")
    parser.add_argument("--output", default="dataset/raw", help="출력 폴더")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if input_path.is_file():
        pdfs = [input_path]
    elif input_path.is_dir():
        pdfs = sorted(input_path.glob("**/*.pdf"))
    else:
        print(f"경로를 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    print(f"PDF {len(pdfs)}개 처리 시작 → {output_dir}")
    total = 0
    for pdf in pdfs:
        print(f"\n[{pdf.name}]")
        total += collect(pdf, output_dir)

    print(f"\n완료: 총 {total}개 이미지 저장 → {output_dir}")
    print("\n다음 단계:")
    print("  1. dataset/raw/ 폴더 열어서 이미지 확인")
    print("  2. chart/  폴더와 table_image/  폴더 만들기")
    print("  3. 이미지를 해당 폴더로 분류 (드래그 앤 드롭)")
    print("  4. 분류 완료 후 finetune_classifier.py 실행")


if __name__ == "__main__":
    main()
