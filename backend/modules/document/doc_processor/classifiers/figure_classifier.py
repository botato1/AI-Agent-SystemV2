"""Figure 유형 분류기.

Vision 모델 없이 픽셀 통계 기반 휴리스틱으로 이미지를 분류합니다.
Docling이 사전에 판단한 힌트가 있으면 그것을 우선합니다.

분류 유형:
    logo        — 브랜드 로고, 아이콘, 배너 (OCR 대상 아님)
    product     — 제품/패키지 사진 (OCR 대상 아님)
    photo       — 일반 사진 (OCR 대상 아님)
    chart       — 막대/선/원형 그래프 (캡션 있으면 OCR 시도)
    diagram     — 프로세스/조직도/플로우차트 (OCR 시도)
    table_image — 이미지로 된 표 (OCR 시도)
    text_image  — 텍스트 밀도 높음 (적극적으로 OCR)
    unknown     — 판단 불가 (기본 worthy_score로 결정)
"""
from __future__ import annotations

from PIL import Image, ImageFilter

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

# ── 픽셀 분석 ─────────────────────────────────────────────────────────────────

def _analyze(image: Image.Image) -> dict[str, float]:
    """이미지 픽셀 통계를 반환합니다.

    Returns:
        mean_gray   : 그레이스케일 평균 (0-255). 높을수록 밝은 배경.
        std_gray    : 그레이스케일 표준편차. 높을수록 내용이 다양.
        dark_ratio  : 어두운 픽셀(< 100) 비율. 높을수록 텍스트/선 많음.
        edge_density: 엣지 픽셀 비율. 높을수록 구조적 내용.
        color_std   : RGB 채널 평균 표준편차. 높을수록 다채로운 색.
    """
    if not _NUMPY_OK:
        return {
            "mean_gray": 128.0, "std_gray": 30.0,
            "dark_ratio": 0.05, "edge_density": 0.05, "color_std": 20.0,
        }

    gray = image.convert("L")
    arr = np.array(gray, dtype=np.float32)

    mean_gray  = float(arr.mean())
    std_gray   = float(arr.std())
    dark_ratio = float((arr < 100).sum()) / max(arr.size, 1)

    # PIL FIND_EDGES — sobel 근사, 추가 의존성 없음
    edge_img  = gray.filter(ImageFilter.FIND_EDGES)
    edge_arr  = np.array(edge_img, dtype=np.float32)
    edge_density = float((edge_arr > 25).sum()) / max(edge_arr.size, 1)

    # 색상 다양성: RGB 각 채널 std의 평균
    rgb = np.array(image.convert("RGB"), dtype=np.float32)
    color_std = float(rgb.std(axis=(0, 1)).mean())

    return {
        "mean_gray":    mean_gray,
        "std_gray":     std_gray,
        "dark_ratio":   dark_ratio,
        "edge_density": edge_density,
        "color_std":    color_std,
    }


# ── 표 격자선 감지 ────────────────────────────────────────────────────────────

def _has_table_grid(image: Image.Image) -> bool:
    """형태학적 연산으로 수평선+수직선 격자 존재 여부를 감지합니다.

    표 이미지의 특징: 수평선 AND 수직선이 일정 이상 존재.
    텍스트 이미지: 수평선만 있거나 둘 다 약함.

    cv2 미설치 시 False 반환 (text_image 유지).
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

    return h_ratio > 0.008 and v_ratio > 0.002


# ── 분류 로직 ─────────────────────────────────────────────────────────────────

def _classify_by_stats(
    stats: dict[str, float],
    area_ratio: float,
    aspect: float,
    top_ratio: float,
) -> str:
    """픽셀 통계 + 레이아웃 정보로 figure 유형을 반환합니다."""
    mg  = stats["mean_gray"]
    dk  = stats["dark_ratio"]
    ed  = stats["edge_density"]
    cs  = stats["color_std"]

    # ── Logo ─────────────────────────────────────────────────────────────────
    # 아주 작은 이미지
    if area_ratio < 0.008:
        return "logo"
    # 페이지 상단 + 작음
    if area_ratio < 0.020 and top_ratio < 0.12:
        return "logo"
    # 배너 형태 (가로로 매우 넓고 얇음)
    if aspect > 8.0 and area_ratio < 0.04:
        return "logo"
    # 단색 + 작음 (아이콘/워터마크)
    if cs < 12.0 and area_ratio < 0.05:
        return "logo"

    # ── Text image ────────────────────────────────────────────────────────────
    # 밝은 배경 + 진한 텍스트 + 엣지 풍부
    if mg > 185 and dk > 0.04 and ed > 0.09:
        return "text_image"
    # 엣지 매우 밀집 (스캔 텍스트)
    if mg > 170 and ed > 0.14:
        return "text_image"

    # ── Table image ───────────────────────────────────────────────────────────
    # 밝은 배경 + 높은 엣지 + 색 단순 (표의 격자선)
    if mg > 200 and ed > 0.07 and cs < 20.0:
        return "table_image"

    # ── Chart ─────────────────────────────────────────────────────────────────
    # 밝은 배경 + 중간 엣지 + 가로 비율 우세 (color_std 상한 완화: 원형 차트 포함)
    if mg > 155 and ed > 0.04 and aspect > 1.15 and cs < 70.0:
        return "chart"
    # 원형 차트: 가로 비율이 정방형에 가깝고 엣지 존재
    if mg > 150 and ed > 0.04 and 0.7 <= aspect <= 1.4 and cs < 70.0:
        return "chart"
    # 색상 풍부한 차트 (파이차트 등): cs 제한 없이 밝고 넓은 이미지
    if mg > 180 and ed > 0.01 and aspect > 1.5 and dk > 0.05:
        return "chart"

    # ── Diagram ──────────────────────────────────────────────────────────────
    # 밝은 배경 + 상당한 엣지 + 색 단순
    if mg > 145 and ed > 0.05 and cs < 50.0:
        return "diagram"

    # ── Product ──────────────────────────────────────────────────────────────
    # 채도 높음 (제품 패키지/사진)
    if cs > 45.0 and 0.015 < area_ratio < 0.30:
        return "product"

    # ── Photo ─────────────────────────────────────────────────────────────────
    # 엣지가 있으면 차트/다이어그램일 수 있으므로 photo 판정 보류
    if cs > 30.0 and ed < 0.02:
        return "photo"

    return "unknown"


# ── 공개 API ──────────────────────────────────────────────────────────────────

def classify(
    image: Image.Image,
    bbox: tuple[float, float, float, float],
    page_size: tuple[float, float],
    docling_hint: str = "unknown",
) -> tuple[str, dict[str, float]]:
    """이미지를 분류하고 (figure_type, pixel_stats)를 반환합니다.

    Args:
        image       : 크롭된 PIL 이미지
        bbox        : (x0, y0, x1, y1) pt 단위
        page_size   : (width, height) pt 단위
        docling_hint: Docling이 사전에 분류한 유형
                      "chart" | "logo" | "unknown" 등

    Returns:
        (figure_type, pixel_stats)
        figure_type : "logo" | "product" | "photo" | "chart" | "diagram"
                      | "table_image" | "text_image" | "unknown"
        pixel_stats : _analyze() 반환값 (worthy_score 계산에 재사용)
    """
    # Docling 힌트 처리
    if docling_hint == "logo":
        # 로고 힌트는 고신뢰 — 픽셀 분석으로도 로고 확인
        stats = _analyze(image)
        return "logo", stats
    if docling_hint == "chart":
        # Docling이 chart라고 판단했으면 chart 유지 — 픽셀 분석으로 뒤집지 않음
        stats = _analyze(image)
        return "chart", stats

    stats = _analyze(image)

    # 정규화: 좌표 역전 방지
    x0 = min(bbox[0], bbox[2])
    y0 = min(bbox[1], bbox[3])
    x1 = max(bbox[0], bbox[2])
    y1 = max(bbox[1], bbox[3])
    pw, ph = page_size
    w, h = x1 - x0, y1 - y0
    area_ratio = (w * h) / (pw * ph) if pw * ph > 0 else 0.0
    aspect     = w / max(h, 1.0)
    top_ratio  = y0 / max(ph, 1.0)

    figure_type = _classify_by_stats(stats, area_ratio, aspect, top_ratio)

    # text_image / unknown으로 분류됐더라도 격자선이 명확히 감지되면 table_image로 재분류
    if figure_type in ("text_image", "unknown", "chart") and _has_table_grid(image):
        figure_type = "table_image"

    return figure_type, stats
