"""열린국회정보 Open API에서 OCR 테스트용 회의록 PDF를 무작위로 수집하는 스크립트.

여러 대수(DAE_NUM)·연도(CONF_DATE) 조합으로 회의 목록을 조회한 뒤,
회의(CONFER_NUM) 단위로 중복 없이 PDF_LINK_URL을 다운로드한다.
(같은 회의라도 안건 개수만큼 행이 반복되므로 회의 단위로 묶어야 한다.)

사용법:
    python backend/modules/document/scripts/collect_assembly_test_pdfs.py --count 60

필요 환경변수:
    ASSEMBLY_API_KEY  (.env에 저장, https://open.assembly.go.kr 에서 발급)
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = os.getenv("ASSEMBLY_API_KEY")
LIST_URL = "https://open.assembly.go.kr/portal/openapi/nzbyfwhwaoanttzje"

# 대수별 국회 임기 대략 연도 범위 (무작위 조합용)
_DAE_YEAR_RANGES = {
    22: range(2024, 2027),
    21: range(2020, 2024),
    20: range(2016, 2020),
    19: range(2012, 2016),
    18: range(2008, 2012),
}


def _sanitize(name: str, max_len: int = 40) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    return name[:max_len] if name else "unnamed"


def fetch_meetings(dae_num: int, conf_year: int, max_pages: int = 3) -> list[dict]:
    """해당 대수/연도의 회의 목록(안건 단위 행)을 여러 페이지에 걸쳐 가져온다."""
    all_rows: list[dict] = []
    for page_index in range(1, max_pages + 1):
        params = {
            "KEY": API_KEY,
            "Type": "json",
            "pIndex": page_index,
            "pSize": 100,
            "DAE_NUM": str(dae_num),
            "CONF_DATE": str(conf_year),
        }
        try:
            resp = requests.get(LIST_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        body = data.get("nzbyfwhwaoanttzje")
        if not body or len(body) < 2:
            break

        rows = body[1].get("row") or []
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            break  # 마지막 페이지
        time.sleep(0.2)

    return all_rows


def download_pdf(url: str) -> bytes | None:
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except Exception:
        return None
    if not resp.content.startswith(b"%PDF"):
        return None
    return resp.content


def main() -> None:
    if not API_KEY:
        print("[에러] ASSEMBLY_API_KEY가 설정되어 있지 않습니다 (.env 확인).")
        sys.exit(1)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=60, help="수집할 PDF 목표 개수")
    parser.add_argument(
        "--out-dir", type=str,
        default=str(Path(__file__).resolve().parents[4] / "storage" / "test_data" / "assembly_minutes"),
        help="PDF 저장 폴더",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = out_dir / "manifest.csv"
    manifest: list[dict] = []
    seen_confer_num: set[str] = set()
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                manifest.append(row)
                seen_confer_num.add(row["confer_num"])
        print(f"[0/2] 기존 manifest {len(manifest)}건 발견 — 이어서 수집합니다.")

    # (대수, 연도) 조합을 무작위로 섞어서 다양한 시기의 회의록을 고루 수집
    combos = [(dae, year) for dae, years in _DAE_YEAR_RANGES.items() for year in years]
    random.shuffle(combos)

    downloaded = 0
    print(f"[1/2] 무작위 대수/연도 조합으로 회의록 PDF {args.count}건 수집 시작...")

    for dae_num, conf_year in combos:
        if downloaded >= args.count:
            break

        rows = fetch_meetings(dae_num, conf_year)
        time.sleep(0.3)
        if not rows:
            continue

        # 같은 회의(CONFER_NUM)는 안건 수만큼 중복되므로 회의 단위로 묶는다.
        meetings: dict[str, dict] = {}
        for row in rows:
            confer_num = str(row.get("CONFER_NUM"))
            if confer_num not in meetings:
                meetings[confer_num] = row

        meeting_list = list(meetings.values())
        random.shuffle(meeting_list)

        for meeting in meeting_list:
            if downloaded >= args.count:
                break

            confer_num = str(meeting.get("CONFER_NUM"))
            if confer_num in seen_confer_num:
                continue

            pdf_url = meeting.get("PDF_LINK_URL")
            if not pdf_url:
                continue

            pdf_bytes = download_pdf(pdf_url)
            time.sleep(0.3)
            if not pdf_bytes:
                continue

            title = meeting.get("TITLE", "")
            filename = f"{_sanitize(title, 50)}_{confer_num}.pdf"
            (out_dir / filename).write_bytes(pdf_bytes)

            downloaded += 1
            seen_confer_num.add(confer_num)
            manifest.append({
                "filename": filename,
                "title": title,
                "class_name": meeting.get("CLASS_NAME", ""),
                "dae_num": meeting.get("DAE_NUM", ""),
                "conf_date": meeting.get("CONF_DATE", ""),
                "confer_num": confer_num,
                "size_bytes": len(pdf_bytes),
            })
            print(f"  [{downloaded}/{args.count}] {filename} ({len(pdf_bytes) / 1024:.0f} KB)")

    print(f"[2/2] 완료 — 이번 실행 {downloaded}건 추가 다운로드 (전체 {len(manifest)}건)")

    with open(manifest_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["filename", "title", "class_name", "dae_num", "conf_date", "confer_num", "size_bytes"],
        )
        writer.writeheader()
        writer.writerows(manifest)
    print(f"  manifest 저장: {manifest_path}")


if __name__ == "__main__":
    main()
