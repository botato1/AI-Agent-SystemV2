"""
Mozilla Common Voice(한국어) 데이터셋을 매니페스트(manifest_cv.jsonl)로 변환.

공식 train/dev/test 분할을 그대로 존중 — 기본은 train.tsv만 사용하고 dev/test는
건드리지 않는다(나중에 우리 자체 평가에 재사용하고 싶을 수 있어 학습에 섞지 않음).
mp3는 서버의 ffmpeg로 16kHz mono wav로 변환해 캐시해두고, 다음 실행 시 이미
변환된 파일은 재사용한다(매번 전체 변환하면 느림).

사용법:
  python make_manifest_commonvoice.py \
    --cv-root /path/to/cv-corpus-26.0-2026-06-12/ko \
    --split train \
    --output manifest_cv.jsonl
"""
import argparse
import csv
import os
import subprocess
import sys

csv.field_size_limit(sys.maxsize)


def convert_to_wav(mp3_path: str, wav_path: str) -> bool:
    if os.path.isfile(wav_path):
        return True
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", mp3_path, "-ar", "16000", "-ac", "1", wav_path],
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv-root", required=True, help="cv-corpus-*/ko 디렉토리 (tsv/clips가 있는 곳)")
    parser.add_argument("--split", default="train", choices=["train", "dev", "test", "validated"])
    parser.add_argument("--output", default="manifest_cv.jsonl")
    parser.add_argument("--wav-dir", default=None, help="변환된 wav 저장 위치 (기본: cv-root/clips_wav)")
    args = parser.parse_args()

    tsv_path = os.path.join(args.cv_root, f"{args.split}.tsv")
    clips_dir = os.path.join(args.cv_root, "clips")
    wav_dir = args.wav_dir or os.path.join(args.cv_root, "clips_wav")
    os.makedirs(wav_dir, exist_ok=True)

    entries, skipped = [], 0
    with open(tsv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)

    print(f"{args.split}.tsv: {len(rows)}개 항목, mp3→wav 변환 시작 (이미 변환된 건 건너뜀)...")
    for i, row in enumerate(rows, 1):
        mp3_name = row["path"]
        text = row["sentence"].strip()
        if not mp3_name or not text:
            skipped += 1
            continue

        mp3_path = os.path.join(clips_dir, mp3_name)
        wav_name = os.path.splitext(mp3_name)[0] + ".wav"
        wav_path = os.path.join(wav_dir, wav_name)

        if not os.path.isfile(mp3_path):
            skipped += 1
            continue
        if not convert_to_wav(mp3_path, wav_path):
            skipped += 1
            continue

        entries.append({
            "source": "commonvoice",
            "audio": os.path.abspath(wav_path),
            "text": text,
            "speaker": row.get("client_id", "unknown")[:16],
        })
        if i % 100 == 0:
            print(f"  진행: {i}/{len(rows)}")

    with open(args.output, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(__import__("json").dumps(entry, ensure_ascii=False) + "\n")

    print(f"매니페스트 생성 완료: {args.output} ({len(entries)}개 항목, 실패/스킵 {skipped}개)")


if __name__ == "__main__":
    main()
