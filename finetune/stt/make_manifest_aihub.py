"""
AI Hub(KconfSpeech 등) 데이터를 매니페스트(manifest_aihub.jsonl)로 변환.

라벨(.txt)과 오디오(.wav)가 zip 안에 동일한 상대 경로로 들어있는 구조를 이용해
경로 매칭으로 짝짓는다 (예: D20/G02/S000314/000016.txt ↔ D20/G02/S000314/000016.wav).

33GB급 오디오 zip을 통째로 재압축 해제하지 않기 위해, 매니페스트에는 실제 파일
경로 대신 "어느 zip의 어느 member인지"만 기록한다 — train_lora.py가 학습 시점에
zip에서 직접 오디오 바이트를 읽는다.

사용법:
  python make_manifest_aihub.py --data-dir /path/to/Training --output manifest_aihub.jsonl
"""
import argparse
import glob
import json
import os
import zipfile


def _build_audio_index(wav_zip_paths):
    """모든 wav zip을 훑어서 {확장자 없는 경로: (zip경로, member명)} 인덱스를 만든다."""
    index = {}
    for zip_path in wav_zip_paths:
        with zipfile.ZipFile(zip_path) as z:
            for member in z.namelist():
                if not member.lower().endswith(".wav"):
                    continue
                key = member[:-4]  # ".wav" 제거
                index[key] = (zip_path, member)
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="라벨/오디오 zip들이 있는 디렉토리 (Training 폴더)")
    parser.add_argument("--output", default="manifest_aihub.jsonl")
    args = parser.parse_args()

    # 파일명에 한글이 섞여있어 인코딩 문제가 잦으므로, 영문 패턴(wav_/label_)으로만 필터링
    all_files = os.listdir(args.data_dir)
    wav_zips = sorted(
        os.path.join(args.data_dir, f) for f in all_files if "wav_" in f and f.endswith(".zip")
    )
    label_zips = sorted(
        os.path.join(args.data_dir, f) for f in all_files if "label_" in f and f.endswith(".zip")
    )
    print(f"오디오 zip {len(wav_zips)}개, 라벨 zip {len(label_zips)}개 발견")
    if not wav_zips or not label_zips:
        raise SystemExit("오디오/라벨 zip을 찾지 못함 — --data-dir 확인 필요")

    print("오디오 인덱스 구축 중 (zip 목록만 읽음, 압축 해제 안 함)...")
    audio_index = _build_audio_index(wav_zips)
    print(f"오디오 인덱스 {len(audio_index)}개 항목")

    entries, skipped = [], 0
    for label_zip in label_zips:
        with zipfile.ZipFile(label_zip) as zl:
            for member in zl.namelist():
                if not member.lower().endswith(".txt"):
                    continue
                key = member[:-4]  # ".txt" 제거
                match = audio_index.get(key)
                if match is None:
                    skipped += 1
                    continue
                audio_zip, audio_member = match
                with zl.open(member) as f:
                    text = f.read().decode("utf-8").strip()
                if not text:
                    skipped += 1
                    continue

                # 경로 구조: D20/G02/S000314/000016 → 화자=S000314, 문장번호=000016
                parts = key.split("/")
                speaker = parts[-2] if len(parts) >= 2 else "unknown"
                sentence_id = parts[-1]

                entries.append({
                    "source": "aihub",
                    "audio_zip": audio_zip,
                    "audio_member": audio_member,
                    "text": text,
                    "speaker": speaker,
                    "sentence_id": sentence_id,
                })

    with open(args.output, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"매니페스트 생성 완료: {args.output} ({len(entries)}개 항목, 매칭 실패 {skipped}개)")


if __name__ == "__main__":
    main()
