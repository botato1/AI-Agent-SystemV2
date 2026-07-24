"""table_image 전용 OCR 모듈

처리 흐름:
  PIL.Image (table_image crop)
  → TableStructureRecognition  →  structure tokens + cell bboxes (px)
  → Cell OCR (Hybrid)
      - 폭 > WIDE_CELL_PX : PaddleOCR (텍스트 셀)
      - 폭 ≤ WIDE_CELL_PX : HoughCircles (체크마크 셀)
  → merge_structure_and_text()  →  HTML
  → html_to_markdown()          →  Markdown (ocr_text 용도)

외부 의존:
  paddleocr.TableStructureRecognition  (SLANet, 이미 캐시됨)
  cv2 (opencv-python) — HoughCircles용
    미설치 시 pixel-density fallback 사용 (정확도 낮음)

공개 API:
  run_table_ocr(image, paddle_engine, tsr=None) -> dict
    {
      "text":             str,         # Markdown (ocr_text로 저장)
      "structure_score":  float,       # TSR 신뢰도
      "cell_count":       int,
      "voting_path":      "tsr_paddle",
    }

  get_or_create_tsr() -> TableStructureRecognition
    lazy singleton — pipeline에서 최초 1회만 로드
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from paddleocr import TableStructureRecognition as _TSR

# ── 상수 ─────────────────────────────────────────────────────────────────────
WIDE_CELL_PX    = 120    # 이 폭 초과 셀 → PaddleOCR (텍스트), 이하 → HoughCircles
HOUGH_DARK_MIN  = 0.07   # 어두운 픽셀 비율 최소값 (빈 셀/격자선 FP 제외)
HOUGH_DARK_MAX  = 0.45   # 어두운 픽셀 비율 최대값 (어두운 텍스트 셀 제외)

# ── lazy TSR singleton ────────────────────────────────────────────────────────
_tsr_instance: "_TSR | None" = None


def get_or_create_tsr() -> "_TSR":
    global _tsr_instance
    if _tsr_instance is None:
        from paddleocr import TableStructureRecognition
        print("[TableOCR] Loading TableStructureRecognition (SLANet)...")
        _tsr_instance = TableStructureRecognition(device="cpu")
        print("[TableOCR] TableStructureRecognition loaded.")
    return _tsr_instance


# ── 셀 bbox 추출 ──────────────────────────────────────────────────────────────
def _crop_cell(image: Image.Image, poly: list[float]) -> Image.Image | None:
    """8점 폴리곤(px)에서 axis-aligned bbox로 crop합니다."""
    xs, ys = poly[0::2], poly[1::2]
    x0 = max(0, int(min(xs)))
    y0 = max(0, int(min(ys)))
    x1 = min(image.width,  int(max(xs)) + 1)
    y1 = min(image.height, int(max(ys)) + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    return image.crop((x0, y0, x1, y1))


# ── 체크마크 감지 (HoughCircles) ──────────────────────────────────────────────
def _detect_checkmark(img: Image.Image) -> str:
    """
    셀 이미지에서 ○ 스타일 마크를 감지합니다.

    HOUGH_DARK_MIN ≤ dark_ratio ≤ HOUGH_DARK_MAX 범위에서만 작동.
    cv2 미설치 시 pixel-density fallback.

    반환: "○" (감지) or "" (없음)
    """
    if img is None or img.width < 5 or img.height < 5:
        return ""

    gray = np.array(img.convert("L"))
    dark_ratio = float(np.sum(gray < 180)) / gray.size

    if dark_ratio < HOUGH_DARK_MIN or dark_ratio > HOUGH_DARK_MAX:
        return ""

    try:
        import cv2
        h, w = gray.shape
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        min_dim = min(h, w)
        min_r = max(3, int(min_dim * 0.15))
        max_r = max(min_r + 2, int(min_dim * 0.45))
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(5, min_dim // 3),
            param1=30,
            param2=15,
            minRadius=min_r,
            maxRadius=max_r,
        )
        return "○" if circles is not None else ""
    except ImportError:
        # cv2 없을 때 pixel-density fallback (덜 정확함)
        h, w = gray.shape
        cy, cx = h // 2, w // 2
        center = gray[max(0, cy - h // 4):cy + h // 4,
                      max(0, cx - w // 4):cx + w // 4]
        if center.size > 0 and float(np.sum(center < 180)) / center.size > 0.2:
            return "○"
        return ""


# ── 셀 텍스트 후처리 ─────────────────────────────────────────────────────────
_CELL_NOISE = re.compile(r"^[\s\W]{1,2}$")   # 특수문자만 1~2자 → 빈칸 처리
_CELL_SPACE_NUM = re.compile(r"\b(\d)(?:\s(\d)){2,}\b")  # "1 2 3" → "123"


def _clean_cell_text(text: str) -> str:
    """셀 텍스트 간단 정규화."""
    if not text:
        return ""
    # 숫자 사이 공백 제거 (3자리 이상)
    text = _CELL_SPACE_NUM.sub(lambda m: m.group(0).replace(" ", ""), text)
    # 단순 노이즈 제거
    if _CELL_NOISE.match(text.strip()):
        return ""
    return text.strip()


# ── PaddleEngine wrapper ─────────────────────────────────────────────────────
def _run_paddle_on_cell(paddle_engine, img: Image.Image) -> str:
    """PaddleEngine으로 셀 이미지 OCR 후 단일 문자열 반환."""
    lines = paddle_engine.run(img)   # PaddleEngine.run(PIL.Image) → list[str]
    raw = " ".join(l.strip() for l in lines if l.strip())
    return _clean_cell_text(raw)


# ── 헤더 정보 파싱 ────────────────────────────────────────────────────────────
def _parse_header_rows(tokens: list[str]) -> int:
    """
    structure 토큰에서 헤더 행 수를 추정합니다.
    첫 번째 <td rowspan="N"> 의 N 값을 반환.
    없으면 1.
    """
    i = 0
    while i < len(tokens):
        if tokens[i] == "<td":
            i += 1
            while i < len(tokens) and tokens[i] != ">":
                m = re.search(r'rowspan="(\d+)"', tokens[i])
                if m:
                    return int(m.group(1))
                i += 1
            break
        i += 1
    return 1


def _normalize_km_label(text: str) -> str:
    """
    컬럼 헤더 셀 텍스트를 정규화합니다.

    "일일 마 점검 1민" → "일일 점검"
    "매 매 1만 2만"    → "매 1만"  (첫 번째 숫자+만 패턴)
    "매만 매 3민"      → "매 3만"
    """
    # 숫자 + 만 패턴 우선
    m = re.search(r'(\d[\d,]*)\s*[만민]', text)
    if m:
        n = m.group(1).replace(",", "")
        return f"매 {n}만"
    # 일일 패턴
    if re.search(r'일일|1일', text):
        return "일일 점검"
    # 점검주기 텍스트 (헤더 아님) → 그대로
    if re.search(r'km|개월', text, re.IGNORECASE):
        return text
    # 1글자 이하 노이즈
    if len(re.sub(r'\W', '', text)) <= 1:
        return ""
    return text


# ── structure + cell_texts 병합 → HTML ───────────────────────────────────────
def _merge_to_html(tokens: list[str], cell_texts: list[str]) -> str:
    """
    structure 토큰과 셀 텍스트를 병합해 완전한 HTML <table>을 생성합니다.

    두 가지 토큰 패턴:
      A) '<td', (attr...), '>', '</td>'  — 멀티 토큰
      B) '<td></td>'                     — 단일 합성 토큰

    헤더 행(row_idx ≤ header_rows)의 셀 텍스트는 _normalize_km_label() 적용.
    """
    header_rows = _parse_header_rows(tokens)
    _SELF_TD = {"<td></td>", "<th></th>"}

    out = []
    cell_idx = 0
    row_idx  = 0
    i = 0

    while i < len(tokens):
        tok = tokens[i]

        if tok == "<tr>":
            out.append(tok)
            row_idx += 1

        elif tok in _SELF_TD:
            tag   = tok[:3]          # "<td" or "<th"
            close = "</td>" if tag == "<td" else "</th>"
            raw   = cell_texts[cell_idx] if cell_idx < len(cell_texts) else ""
            text  = _normalize_km_label(raw) if row_idx <= header_rows else raw
            out.append(f"{tag}>{text}{close}")
            cell_idx += 1

        elif tok in ("<td", "<th"):
            out.append(tok)
            i += 1
            while i < len(tokens) and tokens[i] != ">":
                out.append(tokens[i])
                i += 1
            if i < len(tokens):
                out.append(">")
            raw  = cell_texts[cell_idx] if cell_idx < len(cell_texts) else ""
            text = _normalize_km_label(raw) if row_idx <= header_rows else raw
            out.append(text)
            cell_idx += 1

        else:
            out.append(tok)

        i += 1

    return "".join(out)


# ── HTML → Markdown ───────────────────────────────────────────────────────────
class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell = ""
        self._in = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = ""
            self._in = True

    def handle_endtag(self, tag):
        if tag == "tr":
            if self._row:
                self.rows.append(self._row)
        elif tag in ("td", "th"):
            self._row.append(self._cell.strip())
            self._in = False

    def handle_data(self, data):
        if self._in:
            self._cell += data


def html_to_markdown(html: str) -> str:
    """HTML <table> → GitHub-Flavored Markdown 변환."""
    parser = _TableParser()
    parser.feed(html)
    rows = parser.rows
    if not rows:
        return ""
    mc = max(len(r) for r in rows)
    for r in rows:
        while len(r) < mc:
            r.append("")
    lines = []
    for i, row in enumerate(rows):
        cells = [c.replace("\n", " ").replace("|", "｜") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * mc) + " |")
    return "\n".join(lines)


# ── 공개 진입점 ───────────────────────────────────────────────────────────────
def run_table_ocr(
    image: Image.Image,
    paddle_engine,
    tsr=None,
) -> dict:
    """
    table_image에 대해 TSR + Hybrid Cell OCR을 실행합니다.

    Args:
        image:         table_image crop (PIL.Image, RGB)
        paddle_engine: PaddleEngine 인스턴스 (pipeline._paddle)
        tsr:           TableStructureRecognition 인스턴스 (None이면 lazy 생성)

    Returns:
        dict with keys:
          text            str   Markdown 결과 (ocr_text로 저장)
          structure_score float TSR 신뢰도
          cell_count      int   감지된 셀 수
          voting_path     str   "tsr_paddle"
          sources         list  ["tsr", "paddle", "hough"]
          html            str   HTML 원본 (debug_ocr=True 시 debug 저장용)
    """
    if tsr is None:
        tsr = get_or_create_tsr()

    # ── 1. TSR 실행 ───────────────────────────────────────────────────────────
    arr = np.array(image)
    tsr_results = list(tsr.predict(arr))
    if not tsr_results:
        return {
            "text": "", "confidence": 0.0, "quality_score": 0.0,
            "sources": ["tsr"], "paddle_lines": [], "surya_lines": [],
            "structure_score": 0.0, "cell_count": 0,
            "voting_path": "tsr_paddle", "html": "",
        }
    res = tsr_results[0]

    tokens         = res.get("structure", [])
    bboxes         = res.get("bbox", [])
    structure_score = float(res.get("structure_score", 0.0))

    # ── 2. Cell OCR (Hybrid) ─────────────────────────────────────────────────
    cell_texts: list[str] = []
    used_hough = False

    for poly in bboxes:
        cell_img = _crop_cell(image, poly)
        if cell_img is None or cell_img.width < 5 or cell_img.height < 5:
            cell_texts.append("")
            continue

        if cell_img.width > WIDE_CELL_PX:
            # 텍스트 셀 → 최소 해상도 보장 후 PaddleOCR
            if cell_img.width < 200 or cell_img.height < 30:
                scale = max(200 / cell_img.width, 30 / max(cell_img.height, 1), 1.0)
                cell_img = cell_img.resize(
                    (int(cell_img.width * scale), int(cell_img.height * scale)),
                    Image.LANCZOS,
                )
            text = _run_paddle_on_cell(paddle_engine, cell_img)
        else:
            # 소형 셀 → HoughCircles 먼저, 없으면 PaddleOCR fallback
            text = _detect_checkmark(cell_img)
            if text:
                used_hough = True
            else:
                # Hough 미감지 → Paddle로 재시도 (짧은 텍스트 가능성)
                text = _run_paddle_on_cell(paddle_engine, cell_img)

        cell_texts.append(text)

    # ── 3. HTML / Markdown 생성 ──────────────────────────────────────────────
    html = _merge_to_html(tokens, cell_texts)
    markdown = html_to_markdown(html)

    sources = ["tsr", "paddle"]
    if used_hough:
        sources.append("hough")

    return {
        # pipeline._ocr_from_layout이 기대하는 공통 키
        "text":             markdown,
        "confidence":       round(structure_score, 4),  # voting_confidence 용도
        "quality_score":    round(structure_score, 4),
        "sources":          sources,
        "paddle_lines":     [],   # TSR 경로는 paddle_lines 없음
        "surya_lines":      [],
        # TSR 전용 메타
        "structure_score":  round(structure_score, 4),
        "cell_count":       len(bboxes),
        "voting_path":      "tsr_paddle",
        "html":             html,
    }
