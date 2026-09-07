"""PP-StructureV3(SLANet) 기반 CPU 표 구조 인식 엔진.

PaddleOCR-VL-1.6(GPU 전용)이 쓸 수 없는 환경(GPU 미지원/캐시 권한 문제 등)의
CPU 대체 엔진. VLM이 아니라 표 구조 인식 모델이라 복잡한 표 문맥 이해력은
PaddleOCR-VL-1.6보다 떨어지지만, GPU 없이 동작한다.

PaddleVL16Engine과 동일한 인터페이스(run(image, fig_type) -> str)를 제공해서
pipeline.py의 _flush_vl_queue()가 그대로 재사용할 수 있게 만든다.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Any

import numpy as np
from PIL import Image

if os.name == "nt":
    import site
    for _sp in site.getsitepackages():
        for _d in glob.glob(os.path.join(_sp, "nvidia", "*", "bin")):
            os.add_dll_directory(_d)

os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("FLAGS_use_mkldnn", "0")


def _html_table_to_markdown(html: str) -> str:
    """간단한 HTML <table>을 마크다운 표로 변환합니다 (외부 의존성 없이)."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL)
    md_rows: list[list[str]] = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.IGNORECASE | re.DOTALL)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if cells:
            md_rows.append(cells)
    if not md_rows:
        return ""
    md = "| " + " | ".join(md_rows[0]) + " |\n"
    md += "| " + " | ".join(["---"] * len(md_rows[0])) + " |\n"
    for row in md_rows[1:]:
        md += "| " + " | ".join(row) + " |\n"
    return md.strip()


def _extract_markdown(res: Any) -> str:
    """PPStructureV3 결과 객체에서 표 마크다운을 최대한 방어적으로 추출합니다.

    paddleocr 버전마다 결과 객체 구조(속성 vs dict 키)가 달라질 수 있어서,
    알려진 형태를 순서대로 시도하고 전부 실패하면 빈 문자열을 반환한다.
    호출부(_process_tasks)는 빈 문자열을 "VL 실패, 이미지만 보존"으로
    처리하므로 여기서 예외를 던지지 않는 한 파이프라인이 죽지 않는다.
    """
    md_attr = getattr(res, "markdown", None)
    if md_attr is None and isinstance(res, dict):
        md_attr = res.get("markdown")
    if isinstance(md_attr, dict):
        text = md_attr.get("markdown_texts") or md_attr.get("markdown_text") or ""
        if text:
            return text
    if isinstance(md_attr, str) and md_attr:
        return md_attr

    table_res_list = getattr(res, "table_res_list", None)
    if table_res_list is None and isinstance(res, dict):
        table_res_list = res.get("table_res_list")
    if table_res_list:
        htmls = [t.get("pred_html", "") for t in table_res_list if isinstance(t, dict)]
        html = "\n".join(h for h in htmls if h)
        if html:
            return _html_table_to_markdown(html)

    return ""


class PaddleStructureEngine:
    """PP-StructureV3 기반 CPU 표 인식 엔진 (PaddleVL16Engine의 CPU 대체)."""

    def __init__(self) -> None:
        from paddleocr import PPStructureV3

        self._pipeline = PPStructureV3(
            device="cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_seal_recognition=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
        )

    def run(self, image: Image.Image, fig_type: str = "table_image") -> str:
        try:
            cv_image = np.array(image.convert("RGB"))
            output = self._pipeline.predict(cv_image)
            for res in output:
                md = _extract_markdown(res)
                if md.strip():
                    return md.strip()
            return ""
        except Exception as e:
            print(f"[PP-StructureV3] 추론 실패: {e}")
            return ""
