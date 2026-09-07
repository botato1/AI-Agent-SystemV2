"""OpenDART에서 OCR 정확도 테스트용 PDF를 무작위로 수집하는 스크립트.

상장사 목록에서 무작위로 회사를 뽑아, 최근 정기공시(사업보고서/반기보고서/분기보고서 등)
원문 PDF를 다운로드한다. 보고서 종류는 가리지 않고 무작위로 다양하게 섞는다.

사용법:
    python backend/modules/document/scripts/collect_dart_test_pdfs.py --count 60

필요 환경변수:
    OPENDART_API_KEY  (.env에 저장, https://opendart.fss.or.kr 에서 발급)

주의:
    - PDF 다운로드(pdf/download/main.do)와 뷰어 페이지(dsaf001/main.do)는
      OpenDART 공식 API가 아니라 DART 웹사이트 자체가 제공하는 엔드포인트라
      회사 정책이 바뀌면 동작이 달라질 수 있다.
    - 서버 부담을 줄이기 위해 요청 사이에 짧은 대기를 둔다.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import os
import random
import re
import sys
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import requests
from dotenv import load_dotenv

load_dotenv()

# Windows 콘솔(cp949)에서도 한글/특수문자가 깨지지 않도록 표준출력을 UTF-8로 고정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = os.getenv("OPENDART_API_KEY")
CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
LIST_URL = "https://opendart.fss.or.kr/api/list.json"
VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do"
PDF_INFO_URL = "https://dart.fss.or.kr/pdf/download/main.do"
PDF_FILE_URL = "https://dart.fss.or.kr/pdf/download/pdf.do"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

_DCM_NO_PATTERN = re.compile(r"dcmNo\s*[:=]\s*['\"]?(\d+)")


def _sanitize(name: str, max_len: int = 40) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    return name[:max_len] if name else "unnamed"


def fetch_corp_list() -> list[dict]:
    """상장사(주식코드 보유) 목록을 가져온다."""
    if not API_KEY:
        print("[에러] OPENDART_API_KEY가 설정되어 있지 않습니다 (.env 확인).")
        sys.exit(1)

    resp = requests.get(CORP_CODE_URL, params={"crtfc_key": API_KEY}, timeout=30)
    resp.raise_for_status()

    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
    except zipfile.BadZipFile:
        print(f"[에러] corpCode 응답이 zip이 아닙니다 (API 키 확인 필요): {resp.content[:200]}")
        sys.exit(1)

    xml_bytes = zf.read("CORPCODE.xml")
    root = ElementTree.fromstring(xml_bytes)

    corps = []
    for node in root.findall("list"):
        stock_code = (node.findtext("stock_code") or "").strip()
        if not stock_code:
            continue  # 비상장사는 정기공시가 거의 없어 제외
        corps.append({
            "corp_code": node.findtext("corp_code"),
            "corp_name": node.findtext("corp_name"),
            "stock_code": stock_code,
        })
    return corps


_TODAY = datetime.date.today().strftime("%Y%m%d")
_THREE_YEARS_AGO = (datetime.date.today() - datetime.timedelta(days=365 * 3)).strftime("%Y%m%d")


def find_recent_report(corp_code: str) -> dict | None:
    """해당 회사의 최근 3년치 정기공시(A) 중 1건을 찾는다.

    bgn_de/end_de를 생략하면 OpenDART가 조회 결과를 아예 안 주므로 반드시 지정해야 한다.
    """
    params = {
        "crtfc_key": API_KEY,
        "corp_code": corp_code,
        "pblntf_ty": "A",   # 정기공시(사업/반기/분기보고서 등) - 종류 무관하게 전부 포함
        "bgn_de": _THREE_YEARS_AGO,
        "end_de": _TODAY,
        "page_count": 10,
    }
    try:
        resp = requests.get(LIST_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    if data.get("status") != "000":
        return None

    reports = data.get("list") or []
    if not reports:
        return None
    return random.choice(reports)  # 같은 회사라도 보고서 종류가 섞이도록 무작위 선택


def download_report_pdf(rcept_no: str) -> bytes | None:
    """rcept_no 하나의 원문 PDF를 내려받는다.

    DART는 세션 쿠키가 있어야 실제 PDF 바이트를 내려주므로, 뷰어 페이지 →
    다운로드 안내 페이지 → 실제 파일(pdf.do) 순서로 같은 세션을 유지하며 접근해야 한다.
    (main.do?rcp_no=&dcm_no= 는 "Download" 안내 HTML만 주고, 진짜 파일은 pdf.do 에 있음.)
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        viewer_resp = session.get(
            VIEWER_URL, params={"rcpNo": rcept_no}, timeout=15,
        )
        viewer_resp.raise_for_status()
    except Exception:
        return None

    match = _DCM_NO_PATTERN.search(viewer_resp.text)
    if not match:
        return None
    dcm_no = match.group(1)

    try:
        info_resp = session.get(
            PDF_INFO_URL,
            params={"rcp_no": rcept_no, "dcm_no": dcm_no},
            headers={"Referer": viewer_resp.url},
            timeout=15,
        )
        info_resp.raise_for_status()

        file_resp = session.get(
            PDF_FILE_URL,
            params={"rcp_no": rcept_no, "dcm_no": dcm_no},
            headers={"Referer": info_resp.url},
            timeout=60,
        )
        file_resp.raise_for_status()
    except Exception:
        return None

    if not file_resp.content.startswith(b"%PDF"):
        return None  # 에러 페이지 등 PDF가 아닌 응답
    return file_resp.content


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=60, help="수집할 PDF 목표 개수")
    parser.add_argument(
        "--out-dir", type=str,
        default=str(Path(__file__).resolve().parents[4] / "storage" / "test_data" / "dart_reports"),
        help="PDF 저장 폴더",
    )
    parser.add_argument("--seed", type=int, default=None, help="재현 가능한 무작위 샘플링을 위한 시드")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 기존 manifest가 있으면 이미 받은 rcept_no/회사는 건너뛰고 이어서 수집한다.
    manifest_path = out_dir / "manifest.csv"
    manifest: list[dict] = []
    seen_rcept_no: set[str] = set()
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                manifest.append(row)
                seen_rcept_no.add(row["rcept_no"])
        print(f"[0/3] 기존 manifest {len(manifest)}건 발견 — 이어서 수집합니다.")

    print("[1/3] 상장사 목록 조회 중...")
    corps = fetch_corp_list()
    print(f"  → 상장사 {len(corps)}개 확보")
    random.shuffle(corps)

    downloaded = 0
    tried = 0

    print(f"[2/3] 무작위로 최근 정기공시 PDF {args.count}건 추가 수집 시작...")
    for corp in corps:
        if downloaded >= args.count:
            break
        tried += 1

        report = find_recent_report(corp["corp_code"])
        time.sleep(0.2)
        if not report:
            continue

        rcept_no = report.get("rcept_no")
        if rcept_no in seen_rcept_no:
            continue
        report_nm = report.get("report_nm", "")
        rcept_dt = report.get("rcept_dt", "")

        pdf_bytes = download_report_pdf(rcept_no)
        time.sleep(0.3)
        if not pdf_bytes:
            continue

        filename = f"{_sanitize(corp['corp_name'])}_{_sanitize(report_nm, 20)}_{rcept_no}.pdf"
        (out_dir / filename).write_bytes(pdf_bytes)

        downloaded += 1
        seen_rcept_no.add(rcept_no)
        manifest.append({
            "filename": filename,
            "corp_name": corp["corp_name"],
            "report_nm": report_nm,
            "rcept_no": rcept_no,
            "rcept_dt": rcept_dt,
            "size_bytes": len(pdf_bytes),
        })
        print(f"  [{downloaded}/{args.count}] {filename} ({len(pdf_bytes) / 1024:.0f} KB)")

    print(f"[3/3] 완료 — 이번 실행 시도 {tried}개 회사 중 {downloaded}건 추가 다운로드 (전체 {len(manifest)}건)")

    with open(manifest_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["filename", "corp_name", "report_nm", "rcept_no", "rcept_dt", "size_bytes"],
        )
        writer.writeheader()
        writer.writerows(manifest)
    print(f"  manifest 저장: {manifest_path}")


if __name__ == "__main__":
    main()
