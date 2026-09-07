"""디지털 PDF에서 "폰카메라로 찍은 스캔본"처럼 보이는 합성 이미지 테스트셋을 만든다.

핵심 아이디어:
    디지털 PDF는 이미 정확한 원문 텍스트를 갖고 있으므로, 사람이 정답(.txt)을
    새로 옮겨 적을 필요가 없다. 페이지를 이미지로 렌더링한 뒤 회전/블러/노이즈/
    저조도 등 실제 촬영본에서 흔한 열화를 인위적으로 입히고, 원본 텍스트를
    그대로 정답으로 재사용한다.

사용법:
    python backend/modules/document/scripts/synthesize_scanned_photos.py --count 30

입력: storage/test_data/eval_subset/{dart,assembly}/*.pdf (select_eval_subset.py 결과물)
출력: storage/test_data/eval_subset/scanned_photo/*.jpg + *.txt (같은 이름, 정답 텍스트)
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[4] / "storage" / "test_data"
RENDER_DPI = 200


def _pick_one_page(pdf_path: Path) -> tuple[Image.Image, str] | None:
    """PDF에서 텍스트가 어느 정도 있는 페이지를 무작위로 골라 (이미지, 원문텍스트)로 반환."""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None

    candidates = [i for i in range(len(doc)) if len(doc[i].get_text().strip()) > 200]
    if not candidates:
        doc.close()
        return None

    page_index = random.choice(candidates)
    page = doc[page_index]
    text = page.get_text()

    zoom = RENDER_DPI / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    return image, text


def _add_gaussian_noise(image: Image.Image, sigma: float) -> Image.Image:
    arr = np.array(image).astype(np.int16)
    noise = np.random.normal(0, sigma, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _degrade_like_photo(image: Image.Image) -> Image.Image:
    """실제 폰카메라 촬영본에서 흔한 열화를 무작위 강도로 입힌다."""
    img = image.convert("RGB")

    # 1. 살짝 회전 (문서를 삐딱하게 찍은 것처럼)
    angle = random.uniform(-4.0, 4.0)
    img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255), resample=Image.BICUBIC)

    # 2. 원근감 왜곡 대신 약한 리사이즈 흔들림 (해상도 저하 시뮬레이션)
    scale = random.uniform(0.55, 0.85)
    small = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BILINEAR)
    img = small.resize(img.size, Image.BILINEAR)

    # 3. 블러 (초점 흔들림)
    blur_radius = random.uniform(0.5, 1.8)
    img = img.filter(ImageFilter.GaussianBlur(blur_radius))

    # 4. 밝기/명암 불균일 (조명 환경 재현)
    img = ImageEnhance.Brightness(img).enhance(random.uniform(0.75, 1.15))
    img = ImageEnhance.Contrast(img).enhance(random.uniform(0.8, 1.1))

    # 5. 센서 노이즈
    img = _add_gaussian_noise(img, sigma=random.uniform(4, 12))

    return img


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=30, help="생성할 합성 이미지 개수")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    source_pdfs: list[Path] = []
    for sub in ("dart", "assembly"):
        source_pdfs.extend((BASE_DIR / "eval_subset" / sub).glob("*.pdf"))

    if not source_pdfs:
        print("[에러] storage/test_data/eval_subset/{dart,assembly} 에 PDF가 없습니다.")
        print("       select_eval_subset.py를 먼저 실행하세요.")
        sys.exit(1)

    random.shuffle(source_pdfs)

    out_dir = BASE_DIR / "eval_subset" / "scanned_photo"
    out_dir.mkdir(parents=True, exist_ok=True)

    made = 0
    print(f"[1/1] {len(source_pdfs)}개 원본 PDF 중 {args.count}개를 촬영본처럼 합성...")

    for pdf_path in source_pdfs:
        if made >= args.count:
            break

        result = _pick_one_page(pdf_path)
        if result is None:
            continue
        image, text = result

        degraded = _degrade_like_photo(image)

        stem = pdf_path.stem
        img_path = out_dir / f"{stem}_photo.jpg"
        txt_path = out_dir / f"{stem}_photo.txt"

        degraded.save(img_path, "JPEG", quality=random.randint(55, 80))
        txt_path.write_text(text, encoding="utf-8")

        made += 1
        print(f"  [{made}/{args.count}] {img_path.name}")

    print(f"\n완료 — {made}건 생성 ({out_dir})")


if __name__ == "__main__":
    main()
