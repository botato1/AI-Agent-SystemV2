"""OCR Worthy Score — 애매한 타입에 대한 보조 판단기.

역할:
    FigureClassifier가 "unknown" 또는 "chart"로 판정한 이미지에 한해서만 사용됩니다.
    FigureClassifier가 확정적으로 판단한 타입(text_image, diagram 등)에는 적용하지 않습니다.

호출 조건:
    figure_type in AMBIGUOUS_TYPES ("unknown", "chart") 인 경우에만 호출
    그 외 타입은 pipeline에서 타입 기반으로 직접 결정

가중치:
    size          0.40  — 이미지 절대 크기 (작으면 OCR 의미 없음)
    page_area     0.30  — 페이지 대비 면적 비율
    text_density  0.30  — 픽셀 분석 기반 텍스트 밀도 추정
"""
from __future__ import annotations

# ── 보조 판단 대상 타입 (pipeline에서 이 타입에 한해 worthy_score 호출) ────────
AMBIGUOUS_TYPES: frozenset[str] = frozenset({"unknown", "chart"})

# ── 가중치 (type 가중치 제거 — 타입별 판단은 pipeline에서 수행) ──────────────
_W_SIZE    = 0.40
_W_AREA    = 0.30
_W_DENSITY = 0.30

# ── OCR 실행 임계값 ───────────────────────────────────────────────────────────
OCR_THRESHOLD = 0.70   # 이 미만이면 OCR 스킵 (unknown/chart 타입에만 적용)


def calculate_ocr_worthy_score(
    figure_type: str,
    bbox: tuple[float, float, float, float],
    page_size: tuple[float, float],
    pixel_stats: dict[str, float],
) -> float:
    """unknown/chart 타입에 대한 OCR 보조 판단 점수를 계산합니다.

    이 함수는 figure_type이 AMBIGUOUS_TYPES("unknown", "chart")인 경우에만
    호출됩니다. 확정 타입(text_image, diagram 등)에는 사용하지 않습니다.

    Args:
        figure_type : "unknown" 또는 "chart"
        bbox        : (x0, y0, x1, y1) pt 단위
        page_size   : (width, height) pt 단위
        pixel_stats : figure_classifier._analyze() 반환값

    Returns:
        0.0 ~ 1.0 점수. OCR_THRESHOLD(0.70) 이상이면 OCR 실행.
    """
    # ── 크기 점수 (pt²) ───────────────────────────────────────────────────────
    x0 = min(bbox[0], bbox[2])
    y0 = min(bbox[1], bbox[3])
    x1 = max(bbox[0], bbox[2])
    y1 = max(bbox[1], bbox[3])
    w_pt, h_pt = x1 - x0, y1 - y0
    # 200pt × 100pt 이상이면 만점
    size_score = min((w_pt * h_pt) / (200.0 * 100.0), 1.0)

    # ── 페이지 면적 점수 ──────────────────────────────────────────────────────
    pw, ph = page_size
    page_area = pw * ph
    area_ratio = (w_pt * h_pt) / page_area if page_area > 0 else 0.0
    # 페이지의 10% 이상이면 만점
    area_score = min(area_ratio / 0.10, 1.0)

    # ── 텍스트 밀도 점수 ──────────────────────────────────────────────────────
    edge_density  = pixel_stats.get("edge_density", 0.0)
    density_score = min(edge_density / 0.15, 1.0)

    # ── 합산 ──────────────────────────────────────────────────────────────────
    total = (
        size_score    * _W_SIZE +
        area_score    * _W_AREA +
        density_score * _W_DENSITY
    )

    # ── 대형 figure 보정 ──────────────────────────────────────────────────────
    # unknown/chart 중 페이지의 15% 이상 → OCR 시도 가치 높음
    if area_ratio >= 0.15:
        total += 0.08

    return round(min(total, 1.0), 3)
