"""
AI Hub 매니페스트에서 '학습에 쓰지 않은' 항목만 골라 held-out 평가셋을 만든다.

왜 필요한가:
  기존 평가셋(manifest_eval_hyunsu.jsonl)은 TTS 합성음 40문장이라 잡음/비유창성/
  중복발화가 전혀 없다. 반면 상용 STT 벤치마크(rtzr/Awesome-Korean-Speech-Recognition)는
  AI Hub 실음성으로 CER을 재기 때문에, 우리 수치를 상용 서비스와 비교하려면
  같은 성격의 데이터로 측정해야 한다. (TTS 점수를 상용 수치와 나란히 놓으면 안 됨)

오염 방지:
  학습에 쓴 매니페스트(--exclude)에 등장한 오디오는 전부 제외한다. 이걸 안 하면
  모델이 이미 본 데이터를 평가하는 셈이라 점수가 부풀려진다.

zip 추출:
  evaluate_wer.py는 item["audio"]를 파일 경로로 열지만, AI Hub 매니페스트는
  용량 문제로 zip 내부 위치(audio_zip/audio_member)만 들고 있다. 그래서 평가에
  쓸 항목만 실제 wav 파일로 꺼내 놓고, 그 경로를 가리키는 매니페스트를 새로 쓴다.

사용법:
  python make_heldout_aihub.py --manifest manifest_aihub.jsonl \
      --exclude manifest_aihub_sample.jsonl \
      --count 500 --audio-dir heldout_aihub --output manifest_aihub_heldout.jsonl
"""
import argparse
import json
import os
import random
import zipfile


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="전체 AI Hub 매니페스트 (manifest_aihub.jsonl)")
    parser.add_argument("--exclude", nargs="*", default=[], help="학습에 쓴 매니페스트들 (여기 등장한 오디오는 제외)")
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--audio-dir", default="heldout_aihub", help="추출한 wav를 둘 디렉토리")
    parser.add_argument("--output", default="manifest_aihub_heldout.jsonl")
    parser.add_argument("--seed", type=int, default=42, help="같은 시드면 같은 평가셋 — 재현성 유지용")
    args = parser.parse_args()

    entries = load_jsonl(args.manifest)
    print(f"전체 항목: {len(entries)}개")

    # audio_member는 zip 내부 상대경로(D20/G02/S000314/000016.wav)라 항목마다 고유
    used: set[str] = set()
    for path in args.exclude:
        for item in load_jsonl(path):
            member = item.get("audio_member")
            if member:
                used.add(member)
        print(f"제외 대상 로드: {path} (누적 {len(used)}개)")

    pool = [e for e in entries if e.get("audio_member") and e["audio_member"] not in used]
    print(f"학습 미사용 풀: {len(pool)}개")
    if len(pool) < args.count:
        raise SystemExit(f"풀({len(pool)})이 요청 수({args.count})보다 작음")

    random.seed(args.seed)
    picked = random.sample(pool, args.count)

    os.makedirs(args.audio_dir, exist_ok=True)
    # zip을 항목마다 여는 건 비싸므로 zip 경로별로 묶어서 한 번씩만 연다
    by_zip: dict[str, list[dict]] = {}
    for item in picked:
        by_zip.setdefault(item["audio_zip"], []).append(item)

    out_entries = []
    for zip_path, items in by_zip.items():
        with zipfile.ZipFile(zip_path) as z:
            for item in items:
                member = item["audio_member"]
                # 경로 구분자를 파일명에 안전한 형태로 눌러서 평평하게 저장
                flat_name = member.replace("/", "_")
                dest = os.path.abspath(os.path.join(args.audio_dir, flat_name))
                with z.open(member) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
                out_entries.append({
                    "source": "aihub_heldout",
                    "audio": dest,
                    "text": item["text"],
                    "speaker": item.get("speaker", "unknown"),
                    "sentence_id": item.get("sentence_id", ""),
                })
        print(f"  추출 완료: {os.path.basename(zip_path)} ({len(items)}개)")

    with open(args.output, "w", encoding="utf-8") as f:
        for entry in out_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    speakers = {e["speaker"] for e in out_entries}
    total_chars = sum(len(e["text"].replace(" ", "")) for e in out_entries)
    print(f"\nheld-out 평가셋 생성 완료: {args.output}")
    print(f"  항목 {len(out_entries)}개 / 화자 {len(speakers)}명 / 총 {total_chars}자")
    print(f"  오디오: {os.path.abspath(args.audio_dir)}")


if __name__ == "__main__":
    main()
