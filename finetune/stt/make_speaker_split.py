"""
AI-Hub 화자를 **사람 단위로** 학습셋/평가셋으로 가른다.

왜 필요한가 (2026-08-18):
  화자 판정 개선 가설이 다섯 번 기각됐다(문턱 0.30/0.25/0.15, 점수 z정규화,
  회의 내 프로필 적응, 미상 경계 인정). 공통점은 전부 **판정이 끝난 뒤를 만졌다는 것**이다.
  남은 길은 판정 자체를 잘하게 만드는 것이고, 그 후보가 임베딩 모델 학습이다.

  근거: probe_profile_mismatch.py 실측(회의 3건, 59발화)에서 같은 사람의 회의 내
  유사도가 등록 프로필 유사도보다 평균 +0.20 높았다. 등록과 회의의 조건(마이크·거리·방)이
  다르다는 뜻이고, 지금 쓰는 wespeaker-voxceleb-resnet34-LM은 **영어 데이터로 학습된
  모델**이라 한국어 회의 음성에서 얼마나 무너지는지 자체를 잰 적이 없다.

  AI-Hub 매니페스트에는 화자 라벨이 있다 — 617명, 한 명당 90~1346발화, 총 240,491건.
  임베딩 학습에 쓸 수 있는 규모다.

⚠️ 왜 발화가 아니라 사람 단위로 나누는가:
  화자 인식이 실제로 하는 일은 "처음 보는 두 목소리가 같은 사람인가"를 판단하는 것이다.
  발화 단위로 나누면 같은 사람이 학습과 평가 양쪽에 들어간다. 그러면 모델이 그 사람을
  외운 것인지 목소리를 구분하는 것인지 가릴 수 없고, 점수는 높게 나오지만 **우리 회의
  (모델이 한 번도 본 적 없는 5명)에서는 재현되지 않는다.**
  이건 화자 인식 평가의 기본 규칙이라 타협하지 않는다.

⚠️ ASR 평가셋과의 관계:
  manifest_aihub_heldout*.jsonl은 **전사(ASR) 평가용**이라 여기서 고려하지 않는다.
  화자 임베딩 학습은 전사 모델을 건드리지 않으므로 그쪽 점수를 오염시키지 않는다.
  나중에 ASR까지 파인튜닝하게 되면 그때는 두 격리를 함께 지켜야 한다.

사용법:
  python make_speaker_split.py --manifest manifest_aihub.jsonl --eval-speakers 67
"""
import argparse
import json
import random
from collections import defaultdict


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="manifest_aihub.jsonl")
    parser.add_argument("--eval-speakers", type=int, default=67,
                        help="평가용으로 뺄 사람 수. 나머지는 전부 학습용")
    parser.add_argument("--min-utts", type=int, default=20,
                        help="발화가 이보다 적은 사람은 제외. 같은 사람 쌍을 만들려면 "
                             "한 사람당 발화가 여러 개 있어야 한다")
    parser.add_argument("--seed", type=int, default=42,
                        help="같은 시드면 같은 분할 — 재현성 유지용. 한 번 정하면 바꾸지 말 것")
    parser.add_argument("--out-train", default="manifest_spk_train.jsonl")
    parser.add_argument("--out-eval", default="manifest_spk_eval.jsonl")
    args = parser.parse_args()

    entries = load_jsonl(args.manifest)
    by_speaker: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        spk = e.get("speaker")
        if spk and spk != "unknown":
            by_speaker[spk].append(e)
    print(f"전체 {len(entries)}건 / 화자 {len(by_speaker)}명")

    usable = {s: rows for s, rows in by_speaker.items() if len(rows) >= args.min_utts}
    dropped = len(by_speaker) - len(usable)
    print(f"발화 {args.min_utts}건 미만 제외: {dropped}명 → 사용 가능 {len(usable)}명")
    if len(usable) <= args.eval_speakers:
        raise SystemExit(f"❌ 사용 가능 화자({len(usable)})가 평가용 요청({args.eval_speakers}) 이하")

    speakers = sorted(usable)          # 정렬해두면 시드가 같을 때 결과가 항상 같다
    random.seed(args.seed)
    eval_speakers = set(random.sample(speakers, args.eval_speakers))
    train_speakers = [s for s in speakers if s not in eval_speakers]

    train_rows = [r for s in train_speakers for r in usable[s]]
    eval_rows = [r for s in sorted(eval_speakers) for r in usable[s]]

    # 겹치는 사람이 없어야 한다 — 이 확인이 이 도구의 존재 이유다
    overlap = set(train_speakers) & eval_speakers
    if overlap:
        raise SystemExit(f"❌ 화자가 양쪽에 겹침: {sorted(overlap)[:5]}")

    write_jsonl(args.out_train, train_rows)
    write_jsonl(args.out_eval, eval_rows)

    print()
    print(f"학습셋 {args.out_train}: 화자 {len(train_speakers)}명 / 발화 {len(train_rows)}건")
    print(f"평가셋 {args.out_eval}: 화자 {len(eval_speakers)}명 / 발화 {len(eval_rows)}건")
    print("✅ 두 셋에 겹치는 화자 없음 — 처음 보는 사람으로 평가하게 된다")


if __name__ == "__main__":
    main()
