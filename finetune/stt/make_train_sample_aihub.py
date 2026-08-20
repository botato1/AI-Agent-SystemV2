"""
AI Hub 매니페스트에서 학습용 샘플을 뽑는다 — 평가셋 오염 방지가 핵심 목적.

왜 필요한가:
  manifest_aihub.jsonl은 240,491개인데 학습에는 일부만 쓴다. 그런데 아무렇게나 뽑으면
  held-out 평가셋(manifest_aihub_heldout.jsonl)에 들어있는 항목이 학습에 섞여 들어가서,
  이후 모든 성능 측정이 부풀려진다(모델이 이미 본 데이터를 평가하게 됨).
  그래서 뽑기 전에 "평가에 쓰는 것"을 명시적으로 제외한다.

  make_heldout_aihub.py와 방향이 반대인 도구다:
    - make_heldout_aihub.py : 학습에 쓴 것을 빼고 → 평가셋을 만든다
    - 이 스크립트           : 평가에 쓸 것을 빼고 → 학습셋을 만든다
  둘 다 audio_member(zip 내부 상대경로, 항목마다 고유)를 기준으로 대조한다.

사용법:
  python make_train_sample_aihub.py --manifest manifest_aihub.jsonl \
      --exclude-manifests manifest_aihub_heldout.jsonl \
      --count 25000 --output manifest_aihub_25k.jsonl
"""
import argparse
import json
import random


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def member_of(item: dict) -> str | None:
    """AI Hub 항목은 audio_member로, 추출된 평가셋 항목은 audio 경로로 식별된다.
    make_heldout_aihub.py가 wav를 꺼낼 때 경로 구분자를 '_'로 눌러 저장하므로,
    평가셋 쪽은 파일명에서 원래 member 경로를 되돌려 비교한다."""
    if "audio_member" in item:
        return item["audio_member"]
    audio = item.get("audio")
    if not audio:
        return None
    return audio.rsplit("/", 1)[-1].replace("_", "/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="전체 AI Hub 매니페스트")
    parser.add_argument("--exclude-manifests", nargs="*", default=[],
                        help="학습에서 반드시 빼야 하는 매니페스트들(평가셋 등)")
    parser.add_argument("--count", type=int, default=25000)
    parser.add_argument("--output", default="manifest_aihub_25k.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    entries = load_jsonl(args.manifest)
    print(f"전체 항목: {len(entries)}개")

    excluded: set[str] = set()
    for path in args.exclude_manifests:
        for item in load_jsonl(path):
            m = member_of(item)
            if m:
                excluded.add(m)
        print(f"제외 대상 로드: {path} (누적 {len(excluded)}개)")

    pool = [e for e in entries if e.get("audio_member") and e["audio_member"] not in excluded]
    removed = len(entries) - len(pool)
    print(f"제외 후 풀: {len(pool)}개 (실제로 걸러진 항목 {removed}개)")
    if removed == 0 and excluded:
        # 경로 복원 규칙이 어긋나면 조용히 0개가 걸러져 오염을 놓치게 되므로 즉시 실패시킴
        raise SystemExit("❌ 제외 대상을 하나도 못 걸러냄 — audio_member 대조 규칙 확인 필요")
    if len(pool) < args.count:
        raise SystemExit(f"풀({len(pool)})이 요청 수({args.count})보다 작음")

    random.seed(args.seed)
    picked = random.sample(pool, args.count)
    with open(args.output, "w", encoding="utf-8") as f:
        for e in picked:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    speakers = {e.get("speaker") for e in picked}
    print(f"\n학습 샘플 생성 완료: {args.output}")
    print(f"  항목 {len(picked)}개 / 화자 {len(speakers)}명")


if __name__ == "__main__":
    main()
