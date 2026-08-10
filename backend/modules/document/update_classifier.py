"""파인튜닝된 모델을 figure_classifier.py에 적용합니다.

사용법:
    python update_classifier.py --model ./models/figure_classifier/weights/best.pt
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


MODEL_DEST = Path("doc_processor/classifiers/figure_cls.pt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="파인튜닝된 best.pt 경로")
    args = parser.parse_args()

    src = Path(args.model)
    if not src.exists():
        print(f"[ERROR] 모델 파일 없음: {src}")
        return

    shutil.copy2(src, MODEL_DEST)
    print(f"모델 복사 완료: {src} → {MODEL_DEST}")
    print("서버 재시작하면 새 모델이 적용됩니다.")


if __name__ == "__main__":
    main()
