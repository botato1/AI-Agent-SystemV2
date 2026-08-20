"""
낭독 녹음 파일들을 평가/학습용 매니페스트(manifest.jsonl)로 변환.

녹음 파일명 규칙 {이름}_{문장번호 3자리}.wav 를 script_sentences.json의
정답 텍스트와 자동 매핑한다.

사용법:
  python make_manifest.py --recordings /path/to/recordings --output manifest.jsonl
"""
import argparse
import json
import os
import re

FILENAME_PATTERN = re.compile(r"^(.+)_(\d{3})\.(wav|flac)$")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recordings", required=True, help="녹음 파일들이 있는 디렉토리")
    parser.add_argument("--output", default="manifest.jsonl")
    parser.add_argument(
        "--sentences",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "script_sentences.json"),
    )
    args = parser.parse_args()

    with open(args.sentences, encoding="utf-8") as f:
        sentences = json.load(f)

    entries, skipped = [], []
    for filename in sorted(os.listdir(args.recordings)):
        match = FILENAME_PATTERN.match(filename)
        if not match:
            if not filename.startswith("."):
                skipped.append(filename)
            continue
        speaker, number = match.group(1), match.group(2)
        if number not in sentences:
            skipped.append(f"{filename} (없는 문장번호 {number})")
            continue
        entries.append({
            "audio": os.path.abspath(os.path.join(args.recordings, filename)),
            "text": sentences[number],
            "speaker": speaker,
            "sentence_id": number,
        })

    with open(args.output, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"매니페스트 생성 완료: {args.output} ({len(entries)}개 항목)")
    if skipped:
        print(f"⚠️ 매핑 안 된 파일 {len(skipped)}개 (파일명 규칙 확인 필요):")
        for name in skipped[:10]:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
