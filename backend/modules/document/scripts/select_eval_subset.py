"""수집한 테스트 PDF 중 정답(.txt) 라벨링용 서브셋을 추려서 별도 폴더로 복사한다.

크기(대략 페이지 수/복잡도의 대리 지표)를 기준으로 소/중/대 3구간으로 나눠
구간별로 고르게 뽑는다 — 그래야 짧은 문서에만 치우치지 않는다.

사용법:
    python backend/modules/document/scripts/select_eval_subset.py \
        --dart-n 40 --assembly-n 20
"""
from __future__ import annotations

import argparse
import csv
import random
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[4] / "storage" / "test_data"


def _load_manifest(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _stratified_sample(rows: list[dict], n: int) -> list[dict]:
    """size_bytes 기준 3구간(소/중/대)으로 나눠 최대한 균등하게 n개를 뽑는다."""
    rows = sorted(rows, key=lambda r: int(r["size_bytes"]))
    total = len(rows)
    if total <= n:
        return rows

    third = total // 3
    buckets = [rows[:third], rows[third:third * 2], rows[third * 2:]]

    picked: list[dict] = []
    per_bucket = n // 3
    remainder = n - per_bucket * 3

    for i, bucket in enumerate(buckets):
        take = per_bucket + (1 if i < remainder else 0)
        picked.extend(random.sample(bucket, min(take, len(bucket))))

    # 구간에서 부족했던 만큼 전체 풀에서 보충
    if len(picked) < n:
        remaining_pool = [r for r in rows if r not in picked]
        picked.extend(random.sample(remaining_pool, min(n - len(picked), len(remaining_pool))))

    return picked


def _copy_subset(src_dir: Path, rows: list[dict], dst_dir: Path, size_key: str = "size_bytes") -> list[dict]:
    dst_dir.mkdir(parents=True, exist_ok=True)
    checklist = []
    for row in rows:
        filename = row["filename"]
        src = src_dir / filename
        if not src.exists():
            print(f"  [경고] 원본 없음, 스킵: {filename}")
            continue
        dst = dst_dir / filename
        shutil.copy2(src, dst)
        checklist.append({
            "filename": filename,
            "size_kb": round(int(row[size_key]) / 1024, 1),
            "정답_txt_완료": "",
        })
    return checklist


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dart-n", type=int, default=40, help="DART 문서 중 뽑을 개수")
    parser.add_argument("--assembly-n", type=int, default=20, help="국회 회의록 중 뽑을 개수")
    parser.add_argument("--seed", type=int, default=42, help="재현 가능한 샘플링을 위한 시드")
    args = parser.parse_args()

    random.seed(args.seed)

    eval_dir = BASE_DIR / "eval_subset"
    if eval_dir.exists():
        shutil.rmtree(eval_dir)

    all_checklist: list[dict] = []

    print(f"[1/2] DART 문서에서 {args.dart_n}건 추출...")
    dart_dir = BASE_DIR / "dart_reports"
    dart_rows = _load_manifest(dart_dir / "manifest.csv")
    dart_picked = _stratified_sample(dart_rows, args.dart_n)
    dart_checklist = _copy_subset(dart_dir, dart_picked, eval_dir / "dart")
    for c in dart_checklist:
        c["source"] = "dart"
    all_checklist.extend(dart_checklist)
    print(f"  → {len(dart_checklist)}건 복사 완료")

    print(f"[2/2] 국회 회의록에서 {args.assembly_n}건 추출...")
    assembly_dir = BASE_DIR / "assembly_minutes"
    assembly_rows = _load_manifest(assembly_dir / "manifest.csv")
    assembly_picked = _stratified_sample(assembly_rows, args.assembly_n)
    assembly_checklist = _copy_subset(assembly_dir, assembly_picked, eval_dir / "assembly")
    for c in assembly_checklist:
        c["source"] = "assembly"
    all_checklist.extend(assembly_checklist)
    print(f"  → {len(assembly_checklist)}건 복사 완료")

    checklist_path = eval_dir / "labeling_checklist.csv"
    with open(checklist_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "filename", "size_kb", "정답_txt_완료"])
        writer.writeheader()
        writer.writerows(all_checklist)

    print(f"\n총 {len(all_checklist)}건 → {eval_dir}")
    print(f"라벨링 체크리스트: {checklist_path}")


if __name__ == "__main__":
    main()
