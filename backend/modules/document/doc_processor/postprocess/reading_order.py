from __future__ import annotations

import bisect

from doc_processor.core.models import TextBlock

# 이 비율 이상 폭을 차지하면 컬럼 구분자(제목/박스형 인용문 등)로 간주
_FULL_WIDTH_RATIO = 0.75
# x0(블록 왼쪽 시작점)이 이 거리(콘텐츠 폭 대비) 이내면 같은 컬럼 시작선으로 간주
_X0_CLUSTER_TOL_RATIO = 0.05
# 좌우 클러스터 사이 최소 간격 (콘텐츠 폭 대비) — 이보다 좁으면 진짜 컬럼이 아님
_COLUMN_GAP_RATIO = 0.05
# 컬럼으로 인정하려면 한쪽에 최소 이 개수 이상의 블록(줄)이 있어야 함
# (표 셀처럼 1~2개만 우연히 튀는 경우를 걸러내기 위함)
_MIN_COLUMN_BLOCKS = 3
# 좌우 클러스터의 세로 범위가 이 비율 이상 겹쳐야 "동시에 존재하는 두 컬럼"으로 인정
# (표의 여러 열처럼 서로 다른 세로 구간에 있는 경우를 컬럼으로 오판하지 않기 위함)
_MIN_Y_OVERLAP_RATIO = 0.5
# 진짜 컬럼이라면 문단이 컬럼 폭을 거의 채우므로, 각 클러스터의 중앙값 폭이
# 콘텐츠 폭 대비 최소 이 비율은 돼야 함. "구분/동향"처럼 2~3글자짜리 라벨
# 열(표의 좌측 열)은 이 기준에 못 미쳐 걸러진다.
_MIN_MEDIAN_WIDTH_RATIO = 0.28
# 좌우 클러스터의 중앙값 폭이 서로 이 비율 이상 차이나면(예: 라벨열 vs 제목열처럼
# 비대칭) 컬럼이 아니라 표의 열(라벨-값 쌍)로 판단
_MAX_MEDIAN_WIDTH_RATIO = 2.5
# 같은 행(세로로 겹침)에 왼쪽에 다른 블록이 있으면 전체-폭 구분자가 아니라
# 표의 긴 값 셀일 뿐이므로 구분자에서 제외한다.
_SAME_ROW_OVERLAP_RATIO = 0.4


def restore_reading_order(blocks: list[TextBlock]) -> list[TextBlock]:
    """다단(multi-column) 레이아웃에서 뒤섞인 블록 순서를 복원합니다.

    PyMuPDF의 블록 추출 순서는 PDF 콘텐츠 스트림에 저장된 순서를 그대로
    따르기 때문에, 2단 컬럼 + 박스형 인용문이 섞인 레이아웃에서는 실제
    읽는 순서와 어긋나는 경우가 있다 (예: 왼쪽 컬럼보다 오른쪽 컬럼을
    먼저 읽어버리거나, 박스문단이 중간에 끼어들어 순서가 꼬임).

    전체 폭을 차지하는 블록(제목/박스문단 등)을 구분자 삼아 페이지를
    세로 밴드로 나누고, 각 밴드 안에서 "정확히 2개의 x0 클러스터가
    충분한 블록 수·세로 겹침·비슷한 폭을 가질 때만" 좌우 컬럼으로 판단해
    왼쪽→오른쪽, 각 컬럼 내부는 위→아래 순으로 정렬한다.

    컬럼으로 판단되지 않은 밴드는 **원본 추출 순서를 그대로 보존**한다
    (y좌표로 재정렬하지 않음) — PyMuPDF 원본 순서가 완벽한 y순서는
    아니어도(예: 섹션 헤더와 다음 줄의 y값이 근소하게 뒤바뀜) 대부분
    이미 올바른 읽기 순서이므로, 불필요하게 건드리면 오히려 순서가
    깨진다 (표/목록형 문서에서 실제로 발생했던 회귀).
    """
    if len(blocks) <= 1:
        return blocks

    xs = [b.bbox[0] for b in blocks] + [b.bbox[2] for b in blocks]
    content_x0, content_x1 = min(xs), max(xs)
    content_width = content_x1 - content_x0
    if content_width <= 0:
        return blocks

    full_width_threshold = content_width * _FULL_WIDTH_RATIO

    # 폭이 넓다고 무조건 구분자로 보지 않는다 — 같은 행 왼쪽에 다른 블록이
    # 있으면(예: "1-1." 절 번호 옆의 첫 본문 줄) 페이지를 가로지르는 진짜
    # 구분자가 아니라 그냥 폭이 넓은 일반 콘텐츠일 뿐이다.
    wide_candidates = [b for b in blocks if b.bbox[2] - b.bbox[0] >= full_width_threshold]
    separators = [b for b in wide_candidates if not _has_left_sibling(b, blocks)]

    if not separators:
        return _order_band(blocks, content_width)

    separators.sort(key=lambda b: b.bbox[1])
    boundaries = [s.bbox[1] for s in separators]
    sep_ids = {id(s) for s in separators}

    # 분리자가 아닌 블록을 y좌표 기준 구간(band)에 배정한다.
    # blocks(원본 순서)를 그대로 순회하므로 각 band 내부의 상대 순서는
    # 입력 순서 그대로 유지된다 (컬럼 판정에서 재정렬되기 전까지는).
    band_content: list[list[TextBlock]] = [[] for _ in range(len(boundaries) + 1)]
    for block in blocks:
        if id(block) in sep_ids:
            continue
        idx = bisect.bisect_right(boundaries, block.bbox[1])
        band_content[idx].append(block)

    ordered_bands = [_order_band(band, content_width) for band in band_content]

    result: list[TextBlock] = list(ordered_bands[0])
    for i, sep in enumerate(separators):
        result.append(sep)
        result.extend(ordered_bands[i + 1])
    return result


def _rows_overlap(a: TextBlock, b: TextBlock) -> bool:
    """두 블록이 같은 행(세로로 겹침)에 있는지 확인한다."""
    a_y0, a_y1 = a.bbox[1], a.bbox[3]
    b_y0, b_y1 = b.bbox[1], b.bbox[3]
    overlap = min(a_y1, b_y1) - max(a_y0, b_y0)
    min_h = min(a_y1 - a_y0, b_y1 - b_y0)
    return min_h > 0 and overlap / min_h >= _SAME_ROW_OVERLAP_RATIO


def _has_left_sibling(candidate: TextBlock, blocks: list[TextBlock]) -> bool:
    """candidate와 같은 행에, candidate보다 왼쪽에 있는 블록이 있는지 확인한다.

    있다면 candidate는 페이지 전체를 가로지르는 진짜 구분자가 아니라
    표/목록의 긴 값 셀일 뿐이다 (예: "중립" 라벨 + 그 옆의 긴 설명 텍스트).
    """
    for other in blocks:
        if other is candidate:
            continue
        if other.bbox[2] <= candidate.bbox[0] + 1e-6 and _rows_overlap(candidate, other):
            return True
    return False


def _cluster_by_x0(
    band: list[TextBlock], tol: float
) -> list[list[TextBlock]]:
    """x0 기준으로 가까운 블록끼리 묶는다 (1차원 gap 클러스터링)."""
    by_x0 = sorted(band, key=lambda b: b.bbox[0])
    clusters: list[list[TextBlock]] = [[by_x0[0]]]
    for block in by_x0[1:]:
        if block.bbox[0] - clusters[-1][-1].bbox[0] <= tol:
            clusters[-1].append(block)
        else:
            clusters.append([block])
    return clusters


def _y_range(blocks: list[TextBlock]) -> tuple[float, float]:
    return min(b.bbox[1] for b in blocks), max(b.bbox[3] for b in blocks)


def _median_width(blocks: list[TextBlock]) -> float:
    widths = sorted(b.bbox[2] - b.bbox[0] for b in blocks)
    n = len(widths)
    mid = n // 2
    if n % 2:
        return widths[mid]
    return (widths[mid - 1] + widths[mid]) / 2


def _order_band(band: list[TextBlock], content_width: float) -> list[TextBlock]:
    # 컬럼으로 판단되지 않으면 원본 순서를 그대로 반환한다 (y 재정렬 금지).
    fallback = band
    if len(band) < _MIN_COLUMN_BLOCKS * 2:
        return fallback

    clusters = _cluster_by_x0(band, content_width * _X0_CLUSTER_TOL_RATIO)
    if len(clusters) != 2:
        return fallback

    left, right = clusters
    if len(left) < _MIN_COLUMN_BLOCKS or len(right) < _MIN_COLUMN_BLOCKS:
        return fallback

    # 좌우 사이 실제 간격 확인 (표 셀처럼 딱 붙어있으면 컬럼이 아님)
    left_max_x1 = max(b.bbox[2] for b in left)
    right_min_x0 = min(b.bbox[0] for b in right)
    if right_min_x0 - left_max_x1 < content_width * _COLUMN_GAP_RATIO:
        return fallback

    # 좌우가 세로로 동시에 존재해야 진짜 2단 컬럼 (표의 서로 다른 행/열이
    # 우연히 2개 x0 클러스터로 갈리는 경우를 배제)
    left_y0, left_y1 = _y_range(left)
    right_y0, right_y1 = _y_range(right)
    overlap = min(left_y1, right_y1) - max(left_y0, right_y0)
    min_span = min(left_y1 - left_y0, right_y1 - right_y0)
    if min_span <= 0 or overlap / min_span < _MIN_Y_OVERLAP_RATIO:
        return fallback

    # 진짜 2단 본문이면 양쪽 컬럼의 줄 폭이 비슷해야 함 — 라벨-값 표
    # ("동향" 같은 짧은 라벨 열 + 긴 제목 열)처럼 비대칭이면 컬럼이 아님
    left_median_w = _median_width(left)
    right_median_w = _median_width(right)
    if (
        left_median_w < content_width * _MIN_MEDIAN_WIDTH_RATIO
        or right_median_w < content_width * _MIN_MEDIAN_WIDTH_RATIO
    ):
        return fallback
    wider, narrower = max(left_median_w, right_median_w), min(left_median_w, right_median_w)
    if narrower <= 0 or wider / narrower > _MAX_MEDIAN_WIDTH_RATIO:
        return fallback

    left.sort(key=lambda b: b.bbox[1])
    right.sort(key=lambda b: b.bbox[1])
    return left + right
