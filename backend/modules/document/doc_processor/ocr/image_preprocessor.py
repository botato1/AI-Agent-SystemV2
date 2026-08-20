"""OCR 전 이미지 전처리 모듈

처리 순서:
  1. 최소 해상도 보장 업스케일 (MIN_OCR_PX 기준)
  2. 추가 업스케일 (upscale 파라미터)
  3. 저품질 이미지 전처리
     - 어두운 이미지 → 밝기/대비 자동 보정
     - 흐린 이미지 → 샤프닝
     - 낮은 대비 → CLAHE 또는 PIL 자동 레벨
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

# OCR에 필요한 최소 이미지 폭 (픽셀)
# 이 값 미만이면 자동으로 업스케일
MIN_OCR_PX = 300

# 어두운 이미지 기준 (평균 밝기)
_DARK_THRESHOLD    = 100   # mean_gray < 100 → 밝기 보정
# 낮은 대비 기준 (표준편차)
_LOW_CONTRAST_STD  = 30    # std_gray < 30 → 대비 보정
# 흐린 이미지 기준 (Laplacian variance)
_BLUR_THRESHOLD    = 50    # laplacian_var < 50 → 샤프닝


def _estimate_blur(gray_arr: np.ndarray) -> float:
    """Laplacian variance로 흐림 정도 추정. 값이 낮을수록 흐림."""
    try:
        import cv2
        lap = cv2.Laplacian(gray_arr, cv2.CV_64F)
        return float(lap.var())
    except ImportError:
        # cv2 없으면 PIL FIND_EDGES로 대체
        return 100.0   # 알 수 없으면 샤프닝 스킵


def preprocess_for_ocr(image: Image.Image, upscale: float = 1.0) -> Image.Image:
    """OCR 전 이미지를 전처리합니다.

    Args:
        image:   PIL Image (RGB)
        upscale: 추가 업스케일 배율 (1.0 = 업스케일 없음)

    Returns:
        전처리된 PIL Image
    """
    # ── 1. 최소 해상도 업스케일 ──────────────────────────────────────────────
    min_dim = min(image.width, image.height)
    auto_scale = 1.0
    if min_dim < MIN_OCR_PX:
        auto_scale = MIN_OCR_PX / min_dim

    # 추가 업스케일과 합산
    total_scale = max(auto_scale, upscale)
    if total_scale > 1.01:
        new_w = int(image.width  * total_scale)
        new_h = int(image.height * total_scale)
        image = image.resize((new_w, new_h), Image.LANCZOS)

    # ── 2. 픽셀 통계 분석 ─────────────────────────────────────────────────────
    gray_arr = np.array(image.convert("L"), dtype=np.float32)
    mean_g   = float(gray_arr.mean())
    std_g    = float(gray_arr.std())

    # ── 3. 어두운 이미지 → 밝기 보정 ────────────────────────────────────────
    if mean_g < _DARK_THRESHOLD:
        factor = min(1.8, 200.0 / max(mean_g, 1.0))
        image = ImageEnhance.Brightness(image).enhance(factor)

    # ── 4. 낮은 대비 → 대비 보정 ─────────────────────────────────────────────
    if std_g < _LOW_CONTRAST_STD:
        image = ImageEnhance.Contrast(image).enhance(1.5)

    # ── 5. 흐린 이미지 → 샤프닝 ──────────────────────────────────────────────
    gray_u8 = np.array(image.convert("L"), dtype=np.uint8)
    blur_val = _estimate_blur(gray_u8)
    if blur_val < _BLUR_THRESHOLD:
        image = image.filter(ImageFilter.SHARPEN)
        image = image.filter(ImageFilter.SHARPEN)   # 2회 적용

    return image
