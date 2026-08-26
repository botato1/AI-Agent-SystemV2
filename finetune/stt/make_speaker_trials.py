"""
화자 검증용 **시험 쌍**을 만든다 — 같은 사람 / 다른 사람, **모두 같은 회의 안에서**.

왜 쌍으로 재는가:
  화자 인식의 표준 평가는 "이 두 발화가 같은 사람인가"를 수만 번 물어보고 EER 하나로
  요약하는 방식이다. 우리 파이프라인처럼 "명단 중 누구인가"를 재면 명단 크기·문턱·
  구간 나누기가 전부 섞여 들어가 **모델 자체의 능력을 못 본다.** 여기서는 모델만 떼어낸다.

⚠️ 왜 같은 회의 안에서만 쌍을 만드는가 (2026-08-18에 바뀐 핵심 설계):
  AI-Hub 화자 id는 세션 한정이라 **한 사람은 한 세션에만 존재한다**
  (make_speaker_manifest.py 참고). 그래서 회의를 넘나들며 쌍을 만들면 이렇게 된다:

      같은 사람 쌍 → 항상 같은 회의(같은 방·마이크)
      다른 사람 쌍 → 대개 다른 회의(다른 방·마이크)

  이러면 **"이 두 녹음이 같은 방에서 났나"만 맞혀도 점수가 나온다.** 목소리를 전혀
  구분하지 못해도 EER이 좋게 나올 수 있고, 그 모델을 우리 회의에 가져오면 무너진다.
  화자 인식에서 잘 알려진 실패 방식이다.

  양쪽 다 같은 회의에서 뽑으면 방·마이크가 동일해져 그 단서가 무력해지고,
  남는 차이는 목소리뿐이 된다.

  그리고 이건 타협이 아니다 — **우리 제품이 실제로 하는 일이 한 회의 안의 참석자를
  구분하는 것**이다. 회의를 넘나드는 화자 검증은 우리가 쓰지 않는 능력이다.

⚠️ 길이 필터: 1초 미만은 임베딩이 불안정하다(내용에 휘둘려 목소리 특성이 묻힌다).
   서버도 같은 이유로 _MIN_EMBED_SEC=1.0을 쓴다. 같은 기준을 써야 실제 파이프라인과
   같은 조건이 된다. 매니페스트에 길이가 없어 zip에서 직접 확인한다.

⚠️ zip은 큰 덩어리 몇 개다. 발화마다 새로 열면 매우 느려지므로(전에 다른 도구에서
   229배 느려진 적이 있다) zip 경로별로 묶어서 한 번씩만 연다.

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
                    info = sf.info(io.BytesIO(z.read(item["audio_member"])))
                    if info.frames / info.samplerate >= min_sec:
                        kept.append(item)
                except Exception:
                    continue          # 못 읽는 항목은 평가에 쓸 수 없으니 버린다
        print(f"  길이 확인: {zip_path.split('/')[-1]} ({len(items)}건)")
    print(f"  {checked}건 중 {len(kept)}건이 {min_sec}초 이상")
    return kept


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="manifest_spk_eval.jsonl")
    parser.add_argument("--per-speaker", type=int, default=12,
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
    sessions = {r["session"] for r in rows}
    print(f"평가셋: 세션 {len(sessions)}개 / 화자 {len(by_speaker)}명 / 발화 {len(rows)}건")

    random.seed(args.seed)
    candidates = []
    for spk in sorted(by_speaker):
        pool = by_speaker[spk]
        candidates += random.sample(pool, min(args.per_speaker, len(pool)))
    print(f"후보 {len(candidates)}건 — 길이 확인 시작")
    candidates = keep_long_enough(candidates, args.min_sec)

    # 세션 → 화자 → 발화. 쌍은 이 세션 칸 안에서만 만든다.
    by_session: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in candidates:
        by_session[r["session"]][r["speaker"]].append(r)

    # 같은 사람 쌍을 만들려면 발화가 2개 이상, 다른 사람 쌍을 만들려면 화자가 2명 이상
    pos_sessions = [s for s, spk in by_session.items()
                    if any(len(v) >= 2 for v in spk.values())]
    neg_sessions = [s for s, spk in by_session.items() if len(spk) >= 2]
    print(f"같은 사람 쌍 가능 세션 {len(pos_sessions)}개 / 다른 사람 쌍 가능 세션 {len(neg_sessions)}개")
    if not pos_sessions or not neg_sessions:
        raise SystemExit("❌ 쌍을 만들 수 있는 세션이 없다 — 분할 조건을 완화할 것")

    def key(a, b):
        return tuple(sorted([(a["audio_zip"], a["audio_member"]),
                             (b["audio_zip"], b["audio_member"])]))

    same, diff = set(), set()
    guard = 0
    limit = args.pairs * 300
    while len(same) < args.pairs and guard < limit:
        guard += 1
        spk = by_session[random.choice(pos_sessions)]
        pool = [v for v in spk.values() if len(v) >= 2]
        if not pool:
            continue
        a, b = random.sample(random.choice(pool), 2)
        same.add(key(a, b))

    guard = 0
    while len(diff) < args.pairs and guard < limit:
        guard += 1
        spk = by_session[random.choice(neg_sessions)]
        s1, s2 = random.sample(sorted(spk), 2)
        a, b = random.choice(spk[s1]), random.choice(spk[s2])
        diff.add(key(a, b))

    with open(args.output, "w", encoding="utf-8") as f:
        f.write("label\tzip1\tmember1\tzip2\tmember2\n")
        for label, pairs in ((1, same), (0, diff)):
            for (z1, m1), (z2, m2) in sorted(pairs):
                f.write(f"{label}\t{z1}\t{m1}\t{z2}\t{m2}\n")

    print()
    print(f"✅ {args.output}: 같은 사람 {len(same)}쌍 / 다른 사람 {len(diff)}쌍")
    print("   양쪽 모두 같은 회의 안에서 만들어졌다 — 녹음 환경 차이가 단서가 되지 않는다")
    if len(same) < args.pairs or len(diff) < args.pairs:
        print("⚠️ 요청한 수를 못 채웠다 — --per-speaker나 --eval-sessions를 늘려볼 것")


if __name__ == "__main__":
    main()
