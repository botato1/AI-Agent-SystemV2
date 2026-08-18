"""
화자 검증용 **시험 쌍**을 만든다 (같은 사람 / 다른 사람).

왜 쌍으로 재는가:
  화자 인식의 표준 평가는 "이 두 발화가 같은 사람인가"를 수만 번 물어보고,
  맞히는 정도를 EER 하나로 요약하는 방식이다. 우리 파이프라인처럼 "명단 중 누구인가"를
  재면 명단 크기·문턱·구간 나누기가 전부 섞여 들어가 **모델 자체의 능력을 못 본다.**
  여기서는 모델만 떼어내 잰다.

⚠️ 길이 필터:
  1초 미만 발화는 임베딩이 불안정하다(내용에 휘둘려 목소리 특성이 묻힌다).
  서버도 같은 이유로 _MIN_EMBED_SEC=1.0을 쓴다. 여기서도 같은 기준을 적용해야
  나온 숫자가 실제 파이프라인과 같은 조건이 된다.

  길이는 zip에서 실제로 읽어 확인한다 — 매니페스트에 길이 정보가 없기 때문이다.
  전부 읽으면 비싸므로 **화자당 --per-speaker개만 후보로 뽑아 그것만 확인**한다.

⚠️ zip은 화자별로 흩어져 있지 않고 큰 덩어리 몇 개다. 발화마다 zip을 새로 열면
   매우 느려진다(전에 다른 도구에서 229배 느려진 적이 있다). zip 경로별로 묶어서
   한 번씩만 연다.

사용법:
  python make_speaker_trials.py --manifest manifest_spk_eval.jsonl --pairs 10000
"""
import argparse
import io
import json
import random
import zipfile
from collections import defaultdict

import soundfile as sf

MIN_SEC = 1.0


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def keep_long_enough(rows: list[dict], min_sec: float) -> list[dict]:
    """zip을 경로별로 한 번씩만 열어 길이를 확인하고, 짧은 것을 버린다."""
    by_zip: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_zip[r["audio_zip"]].append(r)

    kept, checked = [], 0
    for zip_path, items in by_zip.items():
        with zipfile.ZipFile(zip_path) as z:
            for item in items:
                checked += 1
                try:
                    data = z.read(item["audio_member"])
                    info = sf.info(io.BytesIO(data))
                    if info.frames / info.samplerate >= min_sec:
                        kept.append(item)
                except Exception:
                    continue          # 못 읽는 항목은 조용히 버린다 — 평가에 쓸 수 없다
        print(f"  길이 확인: {zip_path.split('/')[-1]} ({len(items)}건)")
    print(f"  {checked}건 중 {len(kept)}건이 {min_sec}초 이상")
    return kept


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="manifest_spk_eval.jsonl")
    parser.add_argument("--per-speaker", type=int, default=30,
                        help="화자당 후보 발화 수. 길이 확인 비용을 이 값으로 묶는다")
    parser.add_argument("--pairs", type=int, default=10000,
                        help="같은 사람 쌍의 개수. 다른 사람 쌍도 같은 수만큼 만든다")
    parser.add_argument("--min-sec", type=float, default=MIN_SEC,
                        help=f"이보다 짧은 발화 제외 (서버의 _MIN_EMBED_SEC와 같은 {MIN_SEC})")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="trials_aihub.tsv")
    args = parser.parse_args()

    rows = load_jsonl(args.manifest)
    by_speaker: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_speaker[r["speaker"]].append(r)
    print(f"평가셋: 화자 {len(by_speaker)}명 / 발화 {len(rows)}건")

    random.seed(args.seed)
    candidates = []
    for spk in sorted(by_speaker):
        pool = by_speaker[spk]
        candidates += random.sample(pool, min(args.per_speaker, len(pool)))
    print(f"후보 {len(candidates)}건 — 길이 확인 시작")

    candidates = keep_long_enough(candidates, args.min_sec)

    usable: dict[str, list[dict]] = defaultdict(list)
    for r in candidates:
        usable[r["speaker"]].append(r)
    # 같은 사람 쌍을 만들려면 한 사람에게 발화가 최소 둘 있어야 한다
    usable = {s: v for s, v in usable.items() if len(v) >= 2}
    speakers = sorted(usable)
    if len(speakers) < 2:
        raise SystemExit("❌ 쓸 수 있는 화자가 2명 미만 — 쌍을 만들 수 없다")
    print(f"쌍 생성 가능 화자 {len(speakers)}명")

    same, diff = set(), set()

    def key(a, b):
        return tuple(sorted([(a["audio_zip"], a["audio_member"]),
                             (b["audio_zip"], b["audio_member"])]))

    guard = 0
    while len(same) < args.pairs and guard < args.pairs * 200:
        guard += 1
        spk = random.choice(speakers)
        a, b = random.sample(usable[spk], 2)
        same.add(key(a, b))
    while len(diff) < args.pairs and guard < args.pairs * 400:
        guard += 1
        s1, s2 = random.sample(speakers, 2)
        a, b = random.choice(usable[s1]), random.choice(usable[s2])
        diff.add(key(a, b))

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("label\tzip1\tmember1\tzip2\tmember2\n")
        for label, pairs in ((1, same), (0, diff)):
            for (z1, m1), (z2, m2) in sorted(pairs):
                f.write(f"{label}\t{z1}\t{m1}\t{z2}\t{m2}\n")

    print()
    print(f"✅ {args.output}: 같은 사람 {len(same)}쌍 / 다른 사람 {len(diff)}쌍")
    if len(same) < args.pairs or len(diff) < args.pairs:
        print("⚠️ 요청한 수를 못 채웠다 — 화자나 발화가 부족하다. --per-speaker를 늘려볼 것")


if __name__ == "__main__":
    main()
