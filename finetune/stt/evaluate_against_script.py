"""
회의록을 **정답 대본과 자동으로 대조**해 화자 정확도와 CER을 낸다.

왜 필요한가:
  지금까지는 회의록을 눈으로 읽으며 대본과 맞춰봤다. 느리고, 줄이 늘어나면 놓치고,
  무엇보다 **같은 기준으로 다시 재기가 어렵다** — 코드를 고칠 때마다 "좋아졌나"를
  판단하려면 매번 같은 방식으로 채점해야 하는데 사람 눈은 그러지 못한다.
  실제로 오늘 하루에만 세 번, 눈으로 본 결과로 잘못된 결론을 냈다.

대조 방법:
  전사 세그먼트와 대본 줄은 **개수도 경계도 다르다**(한 줄이 두 세그먼트로 쪼개지거나,
  두 줄이 한 세그먼트로 묶인다). 그래서 순서를 지키면서 글자가 가장 잘 맞도록
  묶는 방법을 찾는다(단조 정렬). 각 대본 줄이 세그먼트 0~N개에 대응할 수 있다.

겹침 줄([겹침] 표시)은 화자 정확도에서 뺀다 — 여러 명이 동시에 말한 줄에서
한 명을 고르는 것 자체가 오답이므로, 맞고 틀림을 따지는 게 의미가 없다.
대신 "겹침으로 감지됐는지"를 따로 보고한다.

사용법:
  python evaluate_against_script.py --meeting <회의ID> \
      --script finetune/stt/scripts/retention_meeting.txt
"""
import argparse
import json
import os
import re
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR  # noqa: E402

_MAX_SEGMENTS_PER_LINE = 4      # 대본 한 줄이 이보다 많은 세그먼트로 쪼개지지는 않는다고 본다


def normalize(text: str) -> str:
    """채점용 정규화 — 공백과 문장부호는 화자 인식·용어 평가와 무관하다."""
    return re.sub(r"[^가-힣a-zA-Z0-9]", "", text)


def cer(reference: str, hypothesis: str) -> tuple[int, int]:
    """(오류 글자 수, 정답 글자 수). 한국어는 어절 경계가 모호해 WER 대신 CER."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return (len(hyp), 0)
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return (previous[-1], len(ref))


def load_script(path: str) -> list[dict]:
    lines = []
    for raw in open(path, encoding="utf-8"):
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        overlapped = raw.startswith("[겹침]")
        if overlapped:
            raw = raw[len("[겹침]"):].strip()
        if ":" not in raw:
            continue
        speaker, text = raw.split(":", 1)
        lines.append({
            "speaker": speaker.strip(), "text": text.strip(), "overlapped": overlapped,
        })
    return lines


def align(script: list[dict], segments: list[dict]) -> list[list[int]]:
    """
    대본 줄마다 어느 세그먼트들이 대응하는지 찾는다(순서 유지).

    한 줄이 여러 세그먼트로 쪼개지거나(화자 경계로 나눴을 때), 세그먼트가 아예 없을
    수도 있다(전사가 통째로 실패). 그래서 "줄 하나 = 세그먼트 0~N개"로 두고
    전체 글자 오류가 가장 작아지는 묶음을 동적 계획법으로 찾는다.
    """
    n, m = len(script), len(segments)
    INF = float("inf")
    # dp[i][j] = 대본 i줄까지, 세그먼트 j개까지 썼을 때 최소 오류
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0

    for i in range(n):
        for j in range(m + 1):
            if dp[i][j] == INF:
                continue
            for take in range(0, min(_MAX_SEGMENTS_PER_LINE, m - j) + 1):
                hyp = " ".join(segments[j + k]["text"] for k in range(take))
                errors, _total = cer(script[i]["text"], hyp)
                if dp[i][j] + errors < dp[i + 1][j + take]:
                    dp[i + 1][j + take] = dp[i][j] + errors
                    back[i + 1][j + take] = (j, take)

    # 마지막 줄까지 갔을 때 세그먼트를 남김없이 쓰는 게 최선이지만, 대본에 없는
    # 잡음 세그먼트가 뒤에 붙을 수 있으므로 최소 비용 지점을 고른다
    best_j = min(range(m + 1), key=lambda j: dp[n][j])
    mapping: list[list[int]] = [[] for _ in range(n)]
    i, j = n, best_j
    while i > 0:
        start, take = back[i][j]
        mapping[i - 1] = list(range(start, start + take))
        i, j = i - 1, start
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--realtime", action="store_true",
                        help="재분석본 대신 실시간 결과(realtime_segments)를 채점")
    args = parser.parse_args()

    meta_path = os.path.join(MEETINGS_DIR, args.meeting, "transcript.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    key = "realtime_segments" if args.realtime else "segments"
    segments = meta.get(key) or []
    if not segments:
        raise SystemExit(f"❌ {key}가 비어 있다")

    script = load_script(os.path.expanduser(args.script))
    mapping = align(script, segments)

    print(f"대상: {'실시간 결과' if args.realtime else '재분석본'} "
          f"(세그먼트 {len(segments)}개 / 대본 {len(script)}줄)\n")
    print(f"{'':4s}{'대본 화자':10s}{'인식 화자':10s}{'':3s}대본 / 인식")
    print("-" * 100)

    correct = wrong = missed = 0
    overlap_lines = []
    total_err = total_ref = 0

    for i, (line, idx) in enumerate(zip(script, mapping), 1):
        hyp = " ".join(segments[k]["text"] for k in idx)
        names = [segments[k].get("speaker") for k in idx]
        got = names[0] if len(set(names)) == 1 and names else (
            "/".join(str(n or "미상") for n in names) if names else None)
        errors, ref_len = cer(line["text"], hyp)
        total_err += errors
        total_ref += ref_len

        if line["overlapped"]:
            flagged = any(segments[k].get("overlapped") for k in idx)
            overlap_lines.append((line, got, flagged))
            mark = "겹침"
        elif got == line["speaker"]:
            correct += 1
            mark = "✅"
        elif got is None or got == "미상":
            missed += 1
            mark = "△"
        else:
            wrong += 1
            mark = "❌"

        print(f"{i:<4d}{line['speaker']:10s}{str(got or '미상'):10s}{mark:3s}"
              f"{line['text'][:38]}")
        if normalize(line["text"]) != normalize(hyp):
            print(f"{'':27s}→ {hyp[:70] or '(전사 없음)'}")

    judged = correct + wrong + missed
    print("-" * 100)
    print(f"화자 정확도: {correct}/{judged} ({correct / max(judged,1) * 100:.0f}%)"
          f"  — 오배정 {wrong}, 미상 {missed}")
    print(f"CER        : {total_err / max(total_ref,1) * 100:.2f}%  "
          f"({total_err}자 오류 / 정답 {total_ref}자)")

    if overlap_lines:
        print(f"\n겹침 줄 {len(overlap_lines)}개 (화자 정확도에서 제외)")
        for line, got, flagged in overlap_lines:
            print(f"  {'겹침 감지됨 ✅' if flagged else '감지 못 함 ❌'}  "
                  f"대본 {line['speaker']} → 인식 {got or '미상'}  |  {line['text'][:40]}")
        detected = sum(1 for _l, _g, f in overlap_lines if f)
        print(f"  → {detected}/{len(overlap_lines)} 감지")
        print("  (감지 못 한 줄에 한 사람 이름이 붙어 있으면, 그건 '여러 명'이 정답인 곳에")
        print("   한 명으로 답한 것이므로 실질적인 오배정이다)")

    print("\n주의: 이 숫자는 '이 회의에서'의 성적이다. 목소리 지문을 만든 회의로 채점하면")
    print("      자기가 만든 데이터로 자기를 채점하는 셈이라 실제보다 좋게 나온다.")


if __name__ == "__main__":
    main()
