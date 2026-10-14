"""
미상(SPEAKER_미상N) 클러스터링 문턱(UNASSIGNED_MERGE_THRESHOLD, 기본 0.75)을
스윕한다 — label_unassigned()이 등록 안 된 낯선 목소리끼리도 "같은 사람이면
같은 번호"로 묶어주길 기대하는데, 0.75는 등록 프로필끼리도 거의 못 넘는 값일
수 있다(2026-09-16 실측, NEXT.md 4a). 이건 "묶음 판정"(등록된 특정 두 사람을
구분)이 실패했던 것과는 다른 질문이다 — 이건 미등록 낯선 목소리끼리 구분이라
데이터가 아예 없다.

여러 사람을 동시에 명단에서 빼고(멀티 홀드아웃), 각자의 발화가:
  ① 같은 사람끼리는 같은 미상 번호로 잘 뭉치는지 (동일인 일치율)
  ② 다른 사람끼리 잘못 같은 번호로 섞이는지 (타인 오염 — 0이어야 안전)
를 잰다.

사용법:
  python sweep_unassigned_merge.py --meeting <회의ID> --script scripts/xxx.txt \
      --names 문지수 김나연 이승주 --exclude 이준오 가동현 \
      --thresholds 0.75 0.6 0.5 0.4
"""
import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)

from stt.core.config import MEETINGS_DIR  # noqa: E402
from evaluate_against_script import load_script, align  # noqa: E402


def sh(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠️ 명령 실패(exit {r.returncode}): {cmd}", file=sys.stderr)
        if r.stderr:
            print(r.stderr, file=sys.stderr)
    return r.stdout


def truth_spans(meeting: str, script_path: str, speaker: str) -> list[tuple[float, float]]:
    """sweep_speaker_floor.py와 동일한 방식."""
    path = os.path.join(MEETINGS_DIR, meeting, "transcript.json")
    with open(path, encoding="utf-8") as f:
        segs = sorted((json.load(f).get("realtime_segments") or []),
                      key=lambda s: s.get("start", 0))
    script = load_script(os.path.expanduser(script_path))
    out = []
    for line, idx in zip(script, align(script, segs)):
        if line["speaker"] != speaker or line["overlapped"] or not idx:
            continue
        out.append((segs[idx[0]]["start"] + 0.3, segs[idx[-1]]["end"] - 0.3))
    return [(s, e) for s, e in out if e - s >= 0.5]


def restart(threshold: float) -> bool:
    sh("kill $(pgrep -f 'uvicorn stt.main:app') 2>/dev/null")
    time.sleep(5)
    subprocess.Popen(
        f"cd {os.path.join(_REPO_ROOT, 'backend', 'modules')} && "
        f"UNASSIGNED_MERGE_THRESHOLD={threshold} nohup python -u -m uvicorn stt.main:app "
        f"--host 0.0.0.0 --port 8002 >> /tmp/stt.log 2>&1 &", shell=True,
    )
    for _ in range(40):
        time.sleep(5)
        if sh("curl -s -o /dev/null -w '%{http_code}' http://localhost:8002/docs") == "200":
            return True
    return False


def refine_with(meeting: str, names: list[str]) -> list[dict]:
    sh(f"cd {_REPO_ROOT} && python finetune/stt/prepare_refine_rerun.py --meeting {meeting} "
       f"--names {' '.join(names)} --profiles-from-global 2>/dev/null")
    sh(f"curl -s -X POST 'http://localhost:8002/api/meetings/{meeting}/refine?force=1'")
    path = os.path.join(MEETINGS_DIR, meeting, "transcript.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("segments") or []


def label_at(segments: list[dict], t: float) -> str | None:
    for s in segments:
        if s["start"] <= t < s["end"]:
            return s.get("speaker")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meeting", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--names", nargs="+", required=True, help="명단에 남길 사람들")
    ap.add_argument("--exclude", nargs="+", required=True, help="명단 밖 — 멀티 홀드아웃")
    ap.add_argument("--thresholds", nargs="+", type=float, default=[0.75, 0.65, 0.55, 0.45])
    args = ap.parse_args()

    spans_by_person = {p: truth_spans(args.meeting, args.script, p) for p in args.exclude}
    for p, spans in spans_by_person.items():
        print(f"{p}: 발화 구간 {len(spans)}개")
    if any(not spans for spans in spans_by_person.values()):
        raise SystemExit("❌ 발화 구간을 못 찾은 사람이 있다 — 대본/회의 확인")

    rows = []
    for threshold in args.thresholds:
        print(f"\n{'=' * 70}\n문턱 {threshold}\n{'=' * 70}")
        if not restart(threshold):
            print("  ❌ 서버가 안 뜬다 — 중단"); break

        segments = refine_with(args.meeting, args.names)

        # 각자 발화 구간마다 어떤 라벨이 붙었는지 모은다
        labels_by_person: dict[str, list[str | None]] = {}
        for person, spans in spans_by_person.items():
            labels = [label_at(segments, (s + e) / 2) for s, e in spans]
            labels_by_person[person] = [lb for lb in labels if lb is not None]

        # ① 동일인 일치율 — 그 사람 구간들이 가장 흔한 라벨로 얼마나 뭉쳤는지
        same_person_consistency = {}
        for person, labels in labels_by_person.items():
            if not labels:
                same_person_consistency[person] = 0.0
                continue
            top_count = Counter(labels).most_common(1)[0][1]
            same_person_consistency[person] = top_count / len(labels)

        # ② 타인 오염 — 서로 다른 두 사람이 **하나라도** 같은 라벨을 받으면 오염.
        # (최빈값끼리만 비교하면 놓친다 — 동점 등으로 최빈값이 우연히 갈려도
        # 실제로는 한쪽 발화 일부가 다른 사람 클러스터에 섞였을 수 있다.)
        label_sets = {
            person: set(labels) for person, labels in labels_by_person.items() if labels
        }
        contaminated_pairs = [
            (p1, p2, label_sets[p1] & label_sets[p2])
            for i, p1 in enumerate(label_sets)
            for p2 in list(label_sets)[i + 1:]
            if label_sets[p1] & label_sets[p2]
        ]

        rows.append((threshold, same_person_consistency, contaminated_pairs, labels_by_person))
        avg_consistency = (
            sum(same_person_consistency.values()) / len(same_person_consistency)
            if same_person_consistency else 0.0
        )
        print(f"  동일인 일치율 평균: {avg_consistency:.0%}  |  타인 오염 쌍: {len(contaminated_pairs)}개")
        for person, labels in labels_by_person.items():
            print(f"    {person}: {labels}")
        for p1, p2, shared in contaminated_pairs:
            print(f"    ⚠️ 오염: {p1} ↔ {p2} 공유 라벨 {shared}")

    print(f"\n{'=' * 70}\n요약\n{'=' * 70}")
    print(f"{'문턱':>6s}{'동일인 일치율(평균)':>18s}{'타인 오염 쌍':>12s}")
    for threshold, consistency, contaminated, _ in rows:
        avg = sum(consistency.values()) / len(consistency) if consistency else 0.0
        print(f"{threshold:6.2f}{avg:17.0%}{len(contaminated):12d}")
    print()
    print("읽는 법")
    print("  동일인 일치율이 높을수록 좋다(같은 사람이 계속 같은 미상 번호를 받음)")
    print("  타인 오염 쌍은 **0이어야 안전하다** — 늘기 시작하는 지점 앞에서 멈출 것")
    print("  (서로 다른 낯선 사람이 같은 미상 번호를 받으면 회의록에서 구분이 안 된다)")


if __name__ == "__main__":
    main()
