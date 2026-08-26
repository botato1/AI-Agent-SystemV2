"""Figure 유형 분류기.

YOLO가 Picture(unknown)로 분류한 이미지에 대해
chart vs table_image 만 구분합니다.

분류 유형:
    table_image — 격자선이 감지된 이미지 표
    chart       — 그 외 모든 이미지 (그래프, 사진, 로고 등)

파인튜닝된 모델이 있으면 (doc_processor/classifiers/figure_cls.pt)
cv2 격자 감지 대신 해당 모델을 사용합니다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False

try:
    import cv2 as _cv2
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

# 파인튜닝된 분류 모델 (존재하면 cv2 대신 사용)
_CLS_MODEL_PATH = Path(__file__).parent / "figure_cls.pt"
_cls_model = None


def _load_cls_model():
    global _cls_model
    if _cls_model is not None:
        return _cls_model
    if not _CLS_MODEL_PATH.exists():
        return None
    try:
        from ultralytics import YOLO
        _cls_model = YOLO(str(_CLS_MODEL_PATH))
        print(f"[FigureClassifier] 파인튜닝 모델 로드: {_CLS_MODEL_PATH}")
    except Exception as e:
        print(f"[FigureClassifier] 모델 로드 실패, cv2 폴백: {e}")
        _cls_model = None
    return _cls_model


def _has_table_grid(image: Image.Image) -> bool:
    """형태학적 연산으로 수평선+수직선 격자 존재 여부를 감지합니다.

    표 이미지의 특징: 수평선 AND 수직선이 일정 이상 존재.
    cv2 미설치 시 False 반환.
    """
    if not _CV2_OK or not _NUMPY_OK:
        return False
    gray = np.array(image.convert("L"), dtype=np.uint8)
    _, binary = _cv2.threshold(gray, 0, 255, _cv2.THRESH_BINARY_INV + _cv2.THRESH_OTSU)
    h, w = binary.shape

    # 수평선: 폭의 25% 이상 이어진 선
    h_kernel = _cv2.getStructuringElement(_cv2.MORPH_RECT, (max(w // 4, 30), 1))
    h_lines  = _cv2.morphologyEx(binary, _cv2.MORPH_OPEN, h_kernel)
    h_ratio  = float(h_lines.sum()) / (255.0 * binary.size)

    # 수직선: 높이의 15% 이상 이어진 선
    v_kernel = _cv2.getStructuringElement(_cv2.MORPH_RECT, (1, max(h // 7, 15)))
    v_lines  = _cv2.morphologyEx(binary, _cv2.MORPH_OPEN, v_kernel)
    v_ratio  = float(v_lines.sum()) / (255.0 * binary.size)

    return h_ratio > 0.020 and v_ratio > 0.008


def classify(image: Image.Image, yolo_table: bool = False) -> str:
    """이미지를 분류하고 figure_type 문자열을 반환합니다.

    파인튜닝된 모델(figure_cls.pt)이 있으면 해당 모델을 사용하고,
    없으면 cv2 격자선 감지로 폴백합니다.

    Args:
        image: 분류할 이미지
        yolo_table: YOLO class 8 (Table)로 감지된 경우 True.

    Returns:
        "table_image" | "chart" | "dialog"
    """
    model = _load_cls_model()
    if model is not None:
        results = model(image, verbose=False)
        cls_id = int(results[0].probs.top1)
        label = results[0].names[cls_id]
        # 학습 시 폴더명이 클래스명 → "chart" / "table_image" / "dialog"
        # dialog는 VL 차트/표 큐를 타지 않고 일반 이미지 OCR로 처리됨
        return label if label in ("chart", "table_image", "dialog") else "chart"

    # cv2 폴백
    has_grid = _has_table_grid(image)
    if yolo_table and not has_grid:
        return "chart"
    if has_grid:
        return "table_image"
    return "chart"