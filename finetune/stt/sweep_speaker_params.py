"""
화자 타임라인 파라미터를 바꿔가며 **같은 오디오로** 재분석해 비교한다.

왜 필요한가 (2026-08-13):
  짧은 발언이 자기 세그먼트를 잃고 옆 사람 발언에 흡수되는 문제가 확인됐다.
  실측(회의 ba8f38c4): 대본 23줄 중 7줄이 '미상'이 됐고, 그 말들은 사라진 게 아니라
  **다른 사람 이름으로 기록**됐다. 모순 감지 제품에서 이건 사라지는 것보다 나쁘다 —
  "아니요 그건 아닌데요"가 앞사람 발언에 붙으면 같은 사람이 자기 말을 뒤집은 것처럼 보인다.

  원인은 세 값이 함께 만든 해상도 한계다:
    SPEAKER_WINDOW_SEC=1.5    1초짜리 발언은 창 하나를 못 채운다
    SPEAKER_SMOOTH_WIDTH=3    3창 다수결 → 약 2.5초보다 짧은 발언은 소수라 지워진다
    SPEAKER_MIN_SUBTURN_SEC=1.0  그걸 통과해도 1초 미만 조각은 버린다

  이 값들은 "맞장구가 긴 발언을 쪼개는 걸 막자"는 목적으로 정해졌다. 제품 우선순위가
  바뀌었으므로 다시 재야 한다. **추측하지 말 것** — 평활을 끄면 같은 사람 목소리도
  문장마다 흔들려 긴 발언이 여러 화자로 쪼개질 수 있다. 그게 평활이 막던 문제다.

무엇을 재나:
  cpCER   전사+화자를 합친 최종 품질 (낮을수록 좋다)
  화자대가 cpCER − DI-cpCER = 화자를 틀려서 잃은 몫
  미상    대본 줄 중 자기 세그먼트를 못 받은 수 (짧은 발언이 흡수된 직접 증거)
  오배정  남의 이름이 붙은 수

  ⚠️ ORC-CER은 거의 안 변해야 정상이다(전사는 안 건드리므로). 크게 변하면 뭔가
     의도치 않은 일이 일어난 것이니 그 조합은 의심할 것.

주의: 조합마다 **서버를 재시작**한다. 회의 중에 돌리지 말 것.

사용법:
  python sweep_speaker_params.py --meeting <회의ID> --script scripts/xxx.txt
"""
import argparse
import os
import re
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_MODULES = os.path.join(_REPO_ROOT, "backend", "modules")

# (이름, 창, 평활, 최소조각)
CONFIGS = [
    ("A 현재",     "1.5", "3", "1.0"),
    ("B 평활끔",   "1.5", "1", "1.0"),
    ("C 최대해상", "1.0", "1", "0.5"),
    ("D 절충",     "1.5", "2", "0.5"),
]


def sh(cmd: str, **kw) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw).stdout


def restart_server(env: dict) -> bool:
    sh("kill $(pgrep -f 'uvicorn stt.main:app') 2>/dev/null")
    time.sleep(5)
    exports = " ".join(f"{k}={v}" for k, v in env.items())
    subprocess.Popen(
        f"cd {_MODULES} && {exports} nohup python -u -m uvicorn stt.main:app "
        f"--host 0.0.0.0 --port 8002 >> /tmp/stt.log 2>&1 &",
        shell=True,
    )
    # 모델 4개를 올리는 데 실측 65초쯤 걸린다. 넉넉히 기다리되 준비되면 바로 진행.
    for _ in range(40):
        time.sleep(5)
        if sh("curl -s -o /dev/null -w '%{http_code}' http://localhost:8002/docs") == "200":
            return True
    return False


def run_one(meeting: str, script: str) -> dict | None:
    # 매번 같은 출발점에서 시작한다 — 이전 재분석 위에 덮어쓰면 무엇과 비교하는지 흐려진다
    sh(f"cd {_REPO_ROOT} && python finetune/stt/prepare_refine_rerun.py "
       f"--meeting {meeting} --profiles-from-global 2>/dev/null")
    sh(f"curl -s -X POST 'http://localhost:8002/api/meetings/{meeting}/refine?force=1'")

    mt = sh(f"cd {_HERE} && python meeteval_score.py --meetings '{meeting}:{script}' 2>/dev/null")
    ev = sh(f"cd {_REPO_ROOT} && python finetune/stt/evaluate_against_script.py "
            f"--meeting {meeting} --script finetune/stt/{script} 2>/dev/null")

    row = re.search(r"^\S*" + re.escape(meeting[:38]) + r"\s*([\d.]+)%\s*([\d.]+)%\s*([\d.]+)%\s*([\d.]+)%",
                    mt, re.M)
    spk = re.search(r"화자 정확도: (\d+)/(\d+).*?오배정 (\d+), 미상 (\d+)", ev)
    if not (row and spk):
        print("   ⚠️ 결과 파싱 실패 — 출력 확인 필요")
        return None
    return {
        "cp": float(row.group(1)), "dicp": float(row.group(2)),
        "orc": float(row.group(3)), "cost": float(row.group(4)),
        "correct": int(spk.group(1)), "total": int(spk.group(2)),
        "wrong": int(spk.group(3)), "missed": int(spk.group(4)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--script", required=True, help="finetune/stt 기준 상대경로")
    args = parser.parse_args()

    results = []
    for name, win, smooth, sub in CONFIGS:
        print(f"\n{'=' * 70}\n{name}  (창 {win} / 평활 {smooth} / 최소조각 {sub})\n{'=' * 70}")
        env = {
            "SPEAKER_WINDOW_SEC": win,
            "SPEAKER_SMOOTH_WIDTH": smooth,
            "SPEAKER_MIN_SUBTURN_SEC": sub,
        }
        print("  서버 재시작 중...")
        if not restart_server(env):
            print("  ❌ 서버가 안 뜬다 — 중단"); break
        print("  재분석·채점 중...")
        got = run_one(args.meeting, args.script)
        if got:
            results.append((name, win, smooth, sub, got))
            print(f"  cpCER {got['cp']:.2f}%  화자대가 {got['cost']:.2f}%  "
                  f"화자 {got['correct']}/{got['total']} (오배정 {got['wrong']}, 미상 {got['missed']})")

    print(f"\n{'=' * 84}")
    print(f"{'조합':14s}{'창':>5s}{'평활':>5s}{'최소':>6s}{'cpCER':>9s}{'화자대가':>9s}"
          f"{'ORC':>8s}{'오배정':>7s}{'미상':>6s}")
    print("-" * 84)
    for name, win, smooth, sub, r in results:
        print(f"{name:14s}{win:>5s}{smooth:>5s}{sub:>6s}{r['cp']:8.2f}%{r['cost']:8.2f}%"
              f"{r['orc']:7.2f}%{r['wrong']:7d}{r['missed']:6d}")
    print()
    print("읽는 법")
    print("  cpCER이 가장 낮은 조합이 최종 품질이 좋다")
    print("  미상이 줄면 짧은 발언이 자기 세그먼트를 되찾은 것 — 이번 수정의 목적")
    print("  ⚠️ 오배정이 늘면 평활을 끈 대가다. 미상이 줄어도 오배정이 그만큼 늘면")
    print("     '모르겠다'가 '틀렸다'로 바뀐 것뿐이라 오히려 나쁘다")
    print("  ⚠️ ORC가 크게 변하면 전사까지 건드린 것이니 그 조합은 의심할 것")
    print()
    print("  회의 한 건 결과다. 방향이 잡히면 나머지 회의로 확인할 것.")


if __name__ == "__main__":
    main()
