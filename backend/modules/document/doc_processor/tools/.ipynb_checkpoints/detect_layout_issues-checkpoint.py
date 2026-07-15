"""파이프라인 결과 JSON에서 YOLO 박스 검출 문제 후보를 자동으로 찾습니다.

찾는 것:
1. 중복 검출 — 같은 page 안에 tables/charts/diagrams 항목의 텍스트가
   서로 많이 겹치는 경우 (완전 중복 또는 유령 박스로 내용이 섞인 경우)
2. 미검출 의심 — figure가 하나도 없는데 페이지가 스캔 이미지라
   원래는 그림/표가 있었을 가능성이 있는 경우 (휴리스틱, 참고용)

사람이 원본 PDF와 대조해서 최종 판단해야 하는 "후보 목록"을 뽑아주는
용도입니다. 이 스크립트가 "문제 있다"고 한 게 실제로 문제인지는
직접 확인이 필요합니다.

사용법:
    python doc_processor/tools/detect_layout_issues.py file1.json file2.json ...
"""
from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SIMILARITY_THRESHOLD = 0.5   # 이 이상 겹치면 의심 후보로 표시
TITLE_SIMILARITY_MIN = 0.7   # 제목이 이보다 안 비슷하면 아예 다른 대상으로 간주하고 스킵
GENERIC_THRESHOLD = 0.9      # 제네릭 제목("차트 데이터" 등)끼리는 이 이상 겹칠 때만 보고

# 제네릭 제목 판별은 assembler와 동일 기준 사용 (단독 실행 시 폴백)
try:
    from doc_processor.output.assembler import _title_is_valid
except Exception:
    def _title_is_valid(t: str) -> bool:  # type: ignore[misc]
        return bool(t and t.strip())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _entry_text(entry: dict) -> str:
    return entry.get("raw_text") or entry.get("markdown") or ""


def _entry_title(entry: dict) -> str:
    """제목 필드가 있으면 그걸, 없으면 raw_text의 첫 줄(### 제목)을 씁니다."""
    if entry.get("title"):
        return entry["title"]
    text = _entry_text(entry)
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line
    return ""


def find_duplicates(doc: dict) -> list[dict]:
    """같은 page 안에서 제목도 비슷하고 텍스트도 겹치는 항목 쌍을 찾습니다.

    제목이 뚜렷이 다르면(예: '대구' vs '6대 광역시') 표 형식이 같아서
    본문이 우연히 비슷해 보여도 진짜 다른 항목일 가능성이 높아 스킵합니다.
    """
    entries: list[dict] = []
    for section in ("tables", "charts", "diagrams"):
        for entry in doc.get(section, []):
            entries.append({
                "section": section,
                "page": entry.get("page"),
                "text": _entry_text(entry),
                "title": _entry_title(entry),
            })

    by_page: dict[int, list[dict]] = {}
    for e in entries:
        by_page.setdefault(e["page"], []).append(e)

    findings = []
    for page, items in by_page.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if not a["text"] or not b["text"]:
                    continue

                # 제목이 둘 다 있고 뚜렷이 다르면 표 형식만 같은 별개 항목으로 보고 스킵
                if a["title"] and b["title"]:
                    title_sim = _similarity(a["title"], b["title"])
                    if title_sim < TITLE_SIMILARITY_MIN:
                        continue

                # 제네릭 제목("차트 데이터", "(% WoW)" 등)끼리는 서로 다른 차트일
                # 가능성이 높아, 본문이 거의 동일할 때만 진짜 중복으로 보고
                generic_pair = not (
                    _title_is_valid(a["title"]) and _title_is_valid(b["title"])
                )
                threshold = GENERIC_THRESHOLD if generic_pair else SIMILARITY_THRESHOLD

                sim = _similarity(a["text"], b["text"])
                if sim >= threshold:
                    findings.append({
                        "page": page,
                        "similarity": round(sim, 2),
                        "section_a": a["section"], "text_a": a["text"][:100],
                        "section_b": b["section"], "text_b": b["text"][:100],
                    })
    return findings


def find_empty_pages(doc: dict) -> list[int]:
    """figure가 하나도 검출 안 된 page 번호를 참고용으로 나열합니다.

    스캔 PDF는 원래 그림/표가 많은 경우가 흔해서, 이 목록은
    "혹시 놓친 게 있는지 원본과 대조해볼 후보"일 뿐입니다.
    """
    pages_with_figures = set()
    for section in ("tables", "charts", "diagrams"):
        for entry in doc.get(section, []):
            pages_with_figures.add(entry.get("page"))

    page_count = doc.get("metadata", {}).get("page_count", 0)
    all_pages = set(range(1, page_count + 1))
    return sorted(all_pages - pages_with_figures)


def main(paths: list[str]) -> None:
    for path in paths:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)

        print(f"\n{'='*60}\n{path}\n{'='*60}")

        dups = find_duplicates(doc)
        if dups:
            print(f"\n[중복 의심] {len(dups)}건")
            for d in dups:
                print(f"  page={d['page']} 유사도={d['similarity']}")
                print(f"    A({d['section_a']}): {d['text_a']}")
                print(f"    B({d['section_b']}): {d['text_b']}")
        else:
            print("\n[중복 의심] 없음")

        empty = find_empty_pages(doc)
        if empty:
            print(f"\n[figure 미검출 페이지 — 원본과 대조 필요] {empty}")
        else:
            print("\n[figure 미검출 페이지] 없음 (모든 페이지에 최소 1개 이상)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python detect_layout_issues.py file1.json file2.json ...")
        sys.exit(1)
    main(sys.argv[1:])