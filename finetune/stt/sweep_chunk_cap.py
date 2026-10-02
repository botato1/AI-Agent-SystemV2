"""
REALTIME_MAX_CHUNK_SEC(최대 청크 길이)를 값별로 바꿔가며 **지연과 전사 품질을 함께** 잰다.

왜 필요한가 (2026-10-02, NEXT.md 10번):
  확정 청크 지연(로그의 latency=)은 정밀 모델이 그 청크를 통째로 전사하는 시간이라
  청크 길이에 비례한다. 최대 길이를 줄이면 지연이 크게 준다(28초 4.64초 → 6초 1.11초).
  하지만 짧을수록 강제 컷이 늘어 문장이 끊기는 부작용이 있어서, 지연만 보고 값을
  고르면 안 된다 — 같은 조건에서 cpCER까지 재서 균형점을 찾는다.

채점은 실시간 결과(realtime_segments)로 한다. 정밀 재분석(segments)은 청크 길이와
무관한 경로라 비교가 안 된다. 재분석이 끝나야 실시간 결과가 realtime_segments로
보존되므로 refined 표시가 붙을 때까지 기다린다.

실시간 청크 경계는 벽시계 기반 VAD 체크라 실행마다 달라질 수 있어서 값마다 반복한다.
서버를 값마다 재기동하므로 **활성 회의가 없을 때만** 돌릴 것.

사용법 (GPU 서버, stt venv, 백그라운드 권장 — 약 50분):
  nohup python sweep_chunk_cap.py > ~/nas_private/chunkcap.log 2>&1 &
"""
import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR  # noqa: E402

LOG_PATH = "/tmp/stt.log"

# (원본 회의 폴더, 대본, 참석자, 짧은 이름) — 소음이 심한 8b5f84b7은 비교가 흔들려 뺀다
MEETINGS = [
    ("ded1105f-6bcd-43fe-8f1f-b7e861b71ade_20260805-081801",
     "scripts/launch_plan_meeting.txt", ["문지수", "김나연", "이승주", "가동현"], "ded"),
    ("ba8f38c4-2eba-4049-ae1d-a0f66533e131_20260812-062851",
     "scripts/search_quality_meeting.txt", ["문지수", "김나연", "이승주", "이준오"], "ba8"),
]


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def restart(cap: int | None) -> bool:
    """cap이 None이면 환경변수 없이(=배포 기본값) 띄운다."""
    sh("kill $(pgrep -f 'uvicorn stt.main:app') 2>/dev/null")
    time.sleep(5)
    env = f"REALTIME_MAX_CHUNK_SEC={cap} " if cap is not None else ""
    subprocess.Popen(
        f"cd {os.path.join(_REPO_ROOT, 'backend', 'modules')} && "
        f"SPEAKER_ABSOLUTE_FLOOR=0.35 {env}nohup python -u -m uvicorn stt.main:app "
        f"--host 0.0.0.0 --port 8002 >> {LOG_PATH} 2>&1 &", shell=True,
    )
    for _ in range(40):
        time.sleep(5)
        if sh("curl -s -o /dev/null -w '%{http_code}' http://localhost:8002/docs") == "200":
            return True
    return False


def count_in_log(substr: str) -> int:
    with open(LOG_PATH, encoding="utf-8", errors="ignore") as f:
        return sum(1 for line in f if substr in line)


def latencies_of(session_id: str) -> list[float]:
    out = []
    marker = f"[{session_id}] 청크 처리 완료"
    with open(LOG_PATH, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if marker in line:
                m = re.search(r"latency=([\d.]+)s", line)
                if m:
                    out.append(float(m.group(1)))
    return out


def wait_refined(meeting_id: str, timeout: int = 240) -> bool:
    path = os.path.join(MEETINGS_DIR, meeting_id, "transcript.json")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("refined") and meta.get("realtime_segments"):
                return True
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(3)
    return False


def score_realtime(meeting_id: str, script: str) -> dict:
    out = subprocess.run(
        [sys.executable, "meeteval_score.py", "--realtime",
         "--meetings", f"{meeting_id}:{os.path.join(_HERE, script)}"],
        cwd=_HERE, capture_output=True, text=True,
    ).stdout
    m = re.search(r"([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%", out)
    if not m:
        return {}
    cp, di, orc, cost, _cpwer = (float(x) for x in m.groups())
    return {"cp": cp, "di": di, "orc": orc, "cost": cost}


def run_one(cap: int, rep: int, meeting: tuple) -> dict | None:
    orig, script, attendees, short = meeting
    session_id = f"chunkcap-{cap}-r{rep}-{short}"
    queue_before = count_in_log("큐 포화")

    out = subprocess.run(
        [sys.executable, "replay_meeting_ws.py", "--meeting", orig,
         "--session-id", session_id, "--attendees", *attendees],
        cwd=_HERE, capture_output=True, text=True,
    ).stdout
    m = re.search(r"meeting_id=(\S+)", out)
    if not m:
        print(f"  ⚠️ {session_id}: 재생 실패 — meeting_id를 못 찾음")
        return None
    meeting_id = m.group(1)

    if not wait_refined(meeting_id):
        print(f"  ⚠️ {session_id}: 재분석이 안 끝남 — 실시간 결과를 못 채점")
        return None
    score = score_realtime(meeting_id, script)
    if not score:
        print(f"  ⚠️ {session_id}: 채점 실패")
        return None

    lats = sorted(latencies_of(session_id))
    row = {
        "cap": cap, "rep": rep, "meeting": short, "meeting_id": meeting_id,
        "chunks": len(lats),
        "lat_mean": statistics.mean(lats) if lats else float("nan"),
        "lat_max": max(lats) if lats else float("nan"),
        "queue_sat": count_in_log("큐 포화") - queue_before,
        **score,
    }
    print(f"  {session_id}: 청크 {row['chunks']}개, 지연 평균 {row['lat_mean']:.2f}s 최대 {row['lat_max']:.2f}s, "
          f"cpCER {row['cp']:.2f}% (순수 전사 {row['di']:.2f}%), 큐포화 {row['queue_sat']}")
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--caps", nargs="+", type=int, default=[28, 15, 10, 6])
    ap.add_argument("--repeats", type=int, default=2)
    args = ap.parse_args()

    total_audio = 117 + 166
    est_min = len(args.caps) * args.repeats * (total_audio + 90) / 60
    print(f"값 {args.caps} × 반복 {args.repeats} × 회의 {len(MEETINGS)}개 — 약 {est_min:.0f}분 예상\n")

    rows: list[dict] = []
    created: list[str] = []
    try:
        for cap in args.caps:
            print(f"{'=' * 60}\nREALTIME_MAX_CHUNK_SEC={cap}\n{'=' * 60}")
            if not restart(cap):
                print("  ❌ 서버가 안 뜬다 — 중단")
                break
            for rep in range(1, args.repeats + 1):
                for meeting in MEETINGS:
                    row = run_one(cap, rep, meeting)
                    if row:
                        rows.append(row)
                        created.append(row["meeting_id"])
    finally:
        print("\n서버를 배포 기본값으로 되돌리는 중...")
        print("  기본값 복구:", "성공" if restart(None) else "❌ 실패 — 수동 재기동 필요")
        for mid in created:
            shutil.rmtree(os.path.join(MEETINGS_DIR, mid), ignore_errors=True)
        print(f"  테스트 회의 {len(created)}개 정리")

    print(f"\n{'=' * 78}\n요약 (값별 평균, 반복·회의 {len(MEETINGS)}개 합산)\n{'=' * 78}")
    print(f"{'최대청크':>8s}{'표본':>6s}{'청크수/런':>10s}{'지연평균':>9s}{'지연최대':>9s}"
          f"{'cpCER':>9s}{'순수전사':>9s}{'큐포화':>7s}")
    for cap in args.caps:
        sel = [r for r in rows if r["cap"] == cap]
        if not sel:
            continue
        avg = lambda k: statistics.mean(r[k] for r in sel)  # noqa: E731
        print(f"{cap:>7d}s{len(sel):>6d}{avg('chunks'):>10.1f}{avg('lat_mean'):>8.2f}s"
              f"{max(r['lat_max'] for r in sel):>8.2f}s{avg('cp'):>8.2f}%{avg('di'):>8.2f}%"
              f"{sum(r['queue_sat'] for r in sel):>7d}")

    print("\n읽는 법")
    print("  지연이 내려가는데 cpCER·순수전사가 거의 안 오르는 값이 채택 후보다.")
    print("  같은 값의 반복끼리 cpCER이 크게 흔들리면(몇 %p) 이 회의로는 비교가 약하다는 뜻.")
    print("  표본은 회의 2개 × 반복 2회뿐이라 작다 — 방향을 보는 용도이지 확정이 아니다.")


if __name__ == "__main__":
    main()
