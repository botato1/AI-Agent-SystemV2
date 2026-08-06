"""
**일반 회의 음성**과 **우리 회의**를 함께 재서, 변경이 어느 쪽을 좋게/나쁘게 했는지 본다.

왜 필요한가 (2026-08-06, 유저 지적에서 출발):
  8월 들어 우리가 녹음한 회의만 보고 개선해왔다. 그러다 보면 **그 회의를 잘 맞히는
  방향으로만 굳어진다** — 용어를 목록에 추가하고, 문턱을 그 회의 분포에 맞추고,
  결과를 그 회의로 채점하는 순환이다. 목표는 "우리 회의를 잘 인식하는 것"이 아니라
  **"어떤 회의를 틀어도 잘 인식하는 것"**이다.

  7월에는 AI-Hub 회의 음성 held-out 500건으로 쟀다(모델 선택·빔 크기·신뢰도 문턱이
  전부 거기서 나왔다). 그런데 8월 들어 그걸 안 돌렸다. **화자 판정을 뜯어고치고,
  턴 자르기를 바꾸고, 용어를 10개 추가하는 동안 일반 음성에서 나빠졌는지 아무도 모른다.**

두 축을 나란히 본다:
  일반 (AI-Hub held-out) — 우리 팀과 무관한 한국어 회의. **여기가 나빠지면 과적합이다.**
  우리 (대본 있는 회의)   — 실제 사용 조건. 여기만 좋아지는 변경은 일반화가 아니다.

용어 목록의 효과도 여기서 갈린다. 우리 용어는 우리 회의에서만 도움이 되고 일반
음성에는 없는 말을 끌어올 수 있다 — `--compare-terms`로 켜고 끈 값을 나란히 낸다.

사용법:
  python benchmark.py --manifest <AI-Hub jsonl> --meetings <회의ID>:<대본> ...
  python benchmark.py --manifest heldout.jsonl --limit 100 --compare-terms
"""
import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))
sys.path.insert(0, _HERE)


_TERMS_FILE = os.path.join(
    _REPO_ROOT, "backend", "modules", "stt", "core", "terms_context.txt",
)


def run_general(manifest: str, limit: int | None, use_terms: bool) -> dict | None:
    """AI-Hub held-out으로 일반 성능을 잰다. evaluate_wer.py를 그대로 쓴다."""
    if limit:
        # evaluate_wer.py에 건수 제한이 없어서 매니페스트를 잘라 임시 파일로 넘긴다
        # (전체 500건은 몇 분 걸린다 — 빠른 확인용 경로가 필요하다)
        trimmed = os.path.join(_HERE, "_bench_manifest.jsonl")
        with open(manifest, encoding="utf-8") as src, open(trimmed, "w", encoding="utf-8") as dst:
            for i, line in enumerate(src):
                if i >= limit:
                    break
                dst.write(line)
        manifest = trimmed

    out = os.path.join(_HERE, f"_bench_general_{'terms' if use_terms else 'noterms'}.json")
    cmd = [
        sys.executable, os.path.join(_HERE, "evaluate_wer.py"),
        "--manifest", manifest, "--output", out,
        # AI-Hub 전사에는 n/ o/ 같은 표기 규약 태그가 있다. 그대로 두면 오류로 잡혀
        # CER이 3.5%p쯤 부풀려진다(실측). 반드시 태그를 걷어내고 비교할 것.
        "--ref-format", "aihub",
    ]
    if use_terms:
        cmd += ["--context", _TERMS_FILE]

    print(f"  일반 평가 실행 중 (용어 {'적용' if use_terms else '없음'})...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️ 실패: {result.stderr.strip()[-400:]}")
        return None
    with open(out, encoding="utf-8") as f:
        return json.load(f)


def run_ours(meeting: str, script: str) -> dict | None:
    """우리 회의를 대본과 대조한다. evaluate_against_script.py의 출력에서 숫자를 뽑는다."""
    result = subprocess.run(
        [sys.executable, os.path.join(_HERE, "evaluate_against_script.py"),
         "--meeting", meeting, "--script", script],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ⚠️ {meeting} 실패: {result.stderr.strip()[-300:]}")
        return None

    import re
    speaker = re.search(r"화자 정확도: (\d+)/(\d+).*?오배정 (\d+), 미상 (\d+)", result.stdout)
    cer = re.search(r"CER\s*:\s*([\d.]+)%", result.stdout)
    if not (speaker and cer):
        print(f"  ⚠️ {meeting}: 출력에서 숫자를 못 찾음")
        return None
    return {
        "correct": int(speaker.group(1)), "total": int(speaker.group(2)),
        "wrong": int(speaker.group(3)), "missed": int(speaker.group(4)),
        "cer": float(cer.group(1)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=None,
                        help="AI-Hub held-out jsonl. 없으면 일반 평가를 건너뛴다")
    parser.add_argument("--limit", type=int, default=None, help="일반 평가 건수 제한(빠른 확인용)")
    parser.add_argument("--meetings", nargs="*", default=[],
                        help="'회의ID:대본경로' 형식. 여러 개 가능")
    parser.add_argument("--compare-terms", action="store_true",
                        help="용어 목록을 켜고 끈 결과를 나란히 낸다 — 우리 용어가 일반 음성을 "
                             "해치는지 보는 유일한 방법")
    args = parser.parse_args()

    print("=" * 78)
    print("일반 회의 음성 (AI-Hub held-out) — 우리 팀과 무관한 데이터")
    print("=" * 78)
    if not args.manifest:
        print("  (--manifest 미지정 — 건너뜀)")
        print("  ⚠️ 일반 평가 없이는 '이 회의만 잘하는 것'과 '전반적으로 잘하는 것'을")
        print("     구분할 수 없다. 개선을 판단하려면 반드시 함께 재야 한다.")
    else:
        with_terms = run_general(args.manifest, args.limit, use_terms=True)
        if with_terms:
            print(f"  용어 적용: CER {with_terms.get('cer', 0) * 100:.2f}%  "
                  f"({with_terms.get('sec_per_item', 0):.2f}초/건)")
        if args.compare_terms:
            without = run_general(args.manifest, args.limit, use_terms=False)
            if without and with_terms:
                delta = (with_terms["cer"] - without["cer"]) * 100
                print(f"  용어 없음: CER {without['cer'] * 100:.2f}%")
                print(f"  → 용어가 일반 음성에 준 영향: {delta:+.2f}%p "
                      f"({'해로움 — 목록이 없는 말을 끌어온다' if delta > 0.3 else '무해' if abs(delta) <= 0.3 else '도움'})")

    print()
    print("=" * 78)
    print("우리 회의 (대본 대조) — 실제 사용 조건")
    print("=" * 78)
    if not args.meetings:
        print("  (--meetings 미지정 — 건너뜀)")
    rows = []
    for spec in args.meetings:
        meeting, script = spec.split(":", 1)
        got = run_ours(meeting, script)
        if got:
            rows.append((meeting, got))
    if rows:
        print(f"{'회의':46s}{'화자정확':>9s}{'오배정':>7s}{'미상':>6s}{'CER':>8s}")
        print("-" * 78)
        for meeting, r in rows:
            pct = r["correct"] / max(r["total"], 1) * 100
            print(f"{meeting[:46]:46s}{pct:8.0f}%{r['wrong']:7d}{r['missed']:6d}{r['cer']:7.2f}%")
        avg_cer = sum(r["cer"] for _m, r in rows) / len(rows)
        total_wrong = sum(r["wrong"] for _m, r in rows)
        print("-" * 78)
        print(f"{'평균/합계':46s}{'':9s}{total_wrong:7d}{'':6s}{avg_cer:7.2f}%")

    print()
    print("=" * 78)
    print("읽는 법")
    print("=" * 78)
    print("  우리 회의만 좋아지고 일반이 나빠졌다 → **과적합.** 그 변경은 되돌리거나 좁혀야 한다")
    print("  둘 다 좋아졌다                      → 진짜 개선")
    print("  일반은 그대로, 우리만 좋아졌다      → 우리 조건(용어·화자)에 특화된 이득.")
    print("                                         나쁘진 않지만 '어떤 회의든'은 아니다")
    print()
    print("  ⚠️ 우리 회의 표본이 적으면 그 숫자도 우연일 수 있다. 회의가 3~4건은 돼야")
    print("     '이 회의에서'가 '대체로'가 된다.")


if __name__ == "__main__":
    main()
