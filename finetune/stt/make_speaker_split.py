"""
AI-Hub 회의 음성을 **세션 단위로** 학습셋/평가셋으로 가른다.

왜 세션 단위인가 (2026-08-18에 화자 단위에서 바꿈):
  AI-Hub 화자 id는 세션 안에서만 유효한 자리 번호라, 전역 화자는 "<세션>_<번호>"로
  만들 수밖에 없다(make_speaker_manifest.py 참고). 그래서 **한 사람은 한 세션에만
  존재한다.** 화자 단위로 나누면 같은 세션이 학습과 평가 양쪽에 걸치게 되고,
  그러면 평가 세션의 녹음 환경을 모델이 이미 학습에서 본 셈이 된다.

  세션째로 갈라야 평가 세션이 **처음 보는 회의**가 된다.

⚠️ 세션 필터: 화자가 2명 미만인 세션은 뺀다.
   같은 세션 안에서 "다른 사람 쌍"을 만들 수 없기 때문이다. 왜 같은 세션 안에서만
   쌍을 만드는지는 make_speaker_trials.py의 주석에 있다 — 요약하면, 그러지 않으면
   모델이 목소리 대신 녹음 환경을 외워도 점수가 나온다.

사용법:
  python make_speaker_split.py --manifest manifest_aihub_speaker.jsonl --eval-sessions 60
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
    parser.add_argument("--manifest", default="manifest_aihub_speaker.jsonl")
    parser.add_argument("--eval-sessions", type=int, default=60,
                        help="평가용으로 뺄 회의 수. 나머지는 전부 학습용")
    parser.add_argument("--min-speakers", type=int, default=2,
                        help="이보다 참가자가 적은 세션은 제외 — 같은 세션 안에서 "
                             "'다른 사람 쌍'을 만들 수 없다")
    parser.add_argument("--min-utts", type=int, default=5,
                        help="발화가 이보다 적은 화자는 제외")
    parser.add_argument("--seed", type=int, default=42,
                        help="같은 시드면 같은 분할 — 한 번 정하면 바꾸지 말 것")
    parser.add_argument("--out-train", default="manifest_spk_train.jsonl")
    parser.add_argument("--out-eval", default="manifest_spk_eval.jsonl")
    args = parser.parse_args()

    rows = load_jsonl(args.manifest)
    by_speaker: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_speaker[r["speaker"]].append(r)
    kept = {s: v for s, v in by_speaker.items() if len(v) >= args.min_utts}
    print(f"전체 {len(rows)}건 / 화자 {len(by_speaker)}명 "
          f"→ 발화 {args.min_utts}건 이상인 화자 {len(kept)}명")

    by_session: dict[str, list[dict]] = defaultdict(list)
    for v in kept.values():
        by_session[v[0]["session"]] += v

    usable = {s: v for s, v in by_session.items()
              if len({r["speaker"] for r in v}) >= args.min_speakers}
    print(f"세션 {len(by_session)}개 → 참가자 {args.min_speakers}명 이상인 세션 {len(usable)}개")
    if len(usable) <= args.eval_sessions:
        raise SystemExit(f"❌ 쓸 수 있는 세션({len(usable)})이 평가용 요청({args.eval_sessions}) 이하")

    sessions = sorted(usable)          # 정렬해야 같은 시드에서 항상 같은 결과가 나온다
    random.seed(args.seed)
    eval_sessions = set(random.sample(sessions, args.eval_sessions))
    train_sessions = [s for s in sessions if s not in eval_sessions]

    train_rows = [r for s in train_sessions for r in usable[s]]
    eval_rows = [r for s in sorted(eval_sessions) for r in usable[s]]

    # 세션이 양쪽에 걸치면 이 분할의 의미가 사라진다 — 반드시 확인한다
    overlap = set(train_sessions) & eval_sessions
    if overlap:
        raise SystemExit(f"❌ 세션이 양쪽에 겹침: {sorted(overlap)[:5]}")

    write_jsonl(args.out_train, train_rows)
    write_jsonl(args.out_eval, eval_rows)

    def speakers(rs):
        return len({r["speaker"] for r in rs})

    print()
    print(f"학습셋 {args.out_train}: 세션 {len(train_sessions)}개 / "
          f"화자 {speakers(train_rows)}명 / 발화 {len(train_rows)}건")
    print(f"평가셋 {args.out_eval}: 세션 {len(eval_sessions)}개 / "
          f"화자 {speakers(eval_rows)}명 / 발화 {len(eval_rows)}건")
    print("✅ 두 셋에 겹치는 세션 없음 — 처음 보는 회의로 평가하게 된다")


if __name__ == "__main__":
    main()
