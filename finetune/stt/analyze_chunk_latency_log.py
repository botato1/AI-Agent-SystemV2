"""
서버 로그에서 확정 청크 지연을 "화자 전환이 있었던 청크"와 "없었던 청크"로 나눠 비교한다.

왜 필요한가 (2026-10-13, NEXT.md 10번):
  profile_precise_pass.py로 잰 정밀 모델 단독 시간은 오디오 1초당 약 0.12~0.18초(RTF)다.
  그런데 서버 로그의 latency=는 그보다 훨씬 크다(15초 설정에서 평균 2.6초).
  realtime_service._transcribe_with_speakers는 청크 전체 전사(precise_task)를 먼저
  띄워두고, 화자 전환이 감지되면 precise_task.cancel()을 부른 뒤 턴별로 다시 전사한다.
  그런데 run_in_executor로 이미 돌고 있는 스레드는 cancel()로 멈추지 않는다 —
  버려진 전체 전사가 GPU에서 끝까지 돌면서 턴별 전사와 같은 GPU를 나눠 쓸 가능성이 있다.
  그렇다면 전환이 있었던 청크만 단독 시간보다 유독 느려야 한다. 이걸 로그로 가른다.

로그 형식:
  🔀 [세션] 청크 안에서 화자 전환 감지 — N개 턴으로 분할 전사     (전환 있을 때만, 완료 줄 직전)
  🎙️ [세션] 청크 처리 완료 (offset=..s, latency=..s, segs=.., speaker=..)

청크 길이는 같은 세션의 다음 청크 offset과의 차로 근사한다(마지막 청크는 제외).

같은 세션 id가 여러 번 쓰이는 경우(sweep_chunk_cap.py의 chunkcap-15-r1-ded 등을 다시
돌리면 이름이 같다)를 위해, 한 세션 안에서 offset이 되돌아가면 별개 실행으로 나눈다.
섞이면 청크 길이(다음 offset과의 차)가 엉터리가 되고 새 데이터와 옛 데이터를 못 가른다.

사용법:
  python analyze_chunk_latency_log.py ~/stt_server_20261013.log /tmp/stt.log
  python analyze_chunk_latency_log.py /tmp/stt.log --prefix chunkcap-15 --last 4
    # 로그 안 chunkcap-15* 실행 중 가장 나중 4개만 (= 방금 돌린 스윕)
"""
import argparse
import re
import statistics
from collections import defaultdict

SPLIT_RE = re.compile(r"🔀 \[([^\]]+)\] 청크 안에서 화자 전환 감지 — (\d+)개 턴")
DONE_RE = re.compile(
    r"\[([^\]]+)\] 청크 처리 완료 \(offset=([\d.]+)s, latency=([\d.]+)s, segs=(\d+)"
)

BUCKETS = [(0, 5), (5, 10), (10, 16), (16, 40)]


def parse(paths: list[str]) -> list[dict]:
    """로그를 읽어 실행(run) 목록을 돌려준다. 각 run = {"sid", "chunks"}, 로그 등장 순서."""
    runs: list[dict] = []
    current: dict[str, dict] = {}   # sid → 지금 쌓고 있는 run
    pending_turns: dict[str, int] = {}
    for path in paths:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = SPLIT_RE.search(line)
                if m:
                    pending_turns[m.group(1)] = int(m.group(2))
                    continue
                m = DONE_RE.search(line)
                if not m:
                    continue
                sid, offset = m.group(1), float(m.group(2))
                run = current.get(sid)
                if run is None or offset < run["chunks"][-1]["offset"]:
                    run = {"sid": sid, "chunks": []}
                    current[sid] = run
                    runs.append(run)
                run["chunks"].append({
                    "offset": offset,
                    "latency": float(m.group(3)),
                    "turns": pending_turns.pop(sid, 0),
                })
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--prefix", default="", help="이 문자열로 시작하는 세션 id만")
    ap.add_argument("--last", type=int, default=0, help="(prefix 적용 후) 가장 나중 N개 실행만")
    args = ap.parse_args()

    runs = [r for r in parse(args.logs) if r["sid"].startswith(args.prefix)]
    if args.last:
        runs = runs[-args.last:]

    rows = []
    used = 0
    for run in runs:
        chunks = run["chunks"]
        # 화자 판정을 쓰는 실행만 본다 — 각자 PC 모드는 전환 분할 경로 자체가 없다
        if not any(c["turns"] for c in chunks):
            continue
        used += 1
        for cur, nxt in zip(chunks, chunks[1:]):
            length = nxt["offset"] - cur["offset"]
            if 0.5 < length < 40:
                rows.append({"len": length, "lat": cur["latency"], "split": cur["turns"] >= 2})

    if not rows:
        raise SystemExit("화자 전환이 기록된 세션이 없다 — 로그 경로·--prefix를 확인할 것")

    n_split = sum(r["split"] for r in rows)
    print(f"실행 {used}개, 청크 {len(rows)}개 (화자 전환 있음 {n_split} / 없음 {len(rows) - n_split})\n")
    print(f"{'청크 길이':>10s}{'구분':>10s}{'개수':>6s}{'평균 길이':>10s}{'평균 지연':>10s}"
          f"{'지연/오디오초':>14s}")
    print("-" * 62)
    for lo, hi in BUCKETS:
        for split in (False, True):
            sel = [r for r in rows if lo <= r["len"] < hi and r["split"] == split]
            if not sel:
                continue
            ml = statistics.mean(r["len"] for r in sel)
            mt = statistics.mean(r["lat"] for r in sel)
            print(f"{f'{lo}~{hi}s':>10s}{'전환 있음' if split else '전환 없음':>10s}{len(sel):>6d}"
                  f"{ml:>9.1f}s{mt:>9.2f}s{mt / ml:>14.2f}")

    print("\n읽는 법")
    print("  '지연/오디오초'는 청크가 길수록 커지는 게 정상이 아니다 — 정밀 모델 단독은 0.12~0.18이다")
    print("  (profile_precise_pass.py). 같은 길이 구간에서 '전환 있음'이 '전환 없음'보다")
    print("  눈에 띄게 크면, 버려진 전체 전사가 GPU를 나눠 쓰고 있다는 뜻이다.")
    print("  둘 다 단독 값(0.12~0.18)보다 크면 전환과 무관한 다른 경합(잠정 스캔 등)이 있다.")


if __name__ == "__main__":
    main()
