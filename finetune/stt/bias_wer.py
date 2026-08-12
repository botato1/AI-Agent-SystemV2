"""
용어 목록의 **이득과 부작용을 갈라서** 잰다 (B-WER / U-WER).

왜 필요한가 (2026-08-10, 문헌 검토에서 출발):
  컨텍스트 바이어싱 분야의 표준 평가는 오류율을 두 갈래로 나눈다.

    B-WER  용어 목록에 있는 단어들의 오류율  → **이득**
    U-WER  목록에 없는 단어들의 오류율      → **부작용(과도한 바이어싱)**

  좋은 바이어싱은 **B-WER을 낮추면서 U-WER을 안 올리는 것**이다. 전체 WER 하나만
  보면 이 둘이 상쇄돼 판단이 안 선다.

  우리가 실제로 그 함정에 빠졌다. `온보딩`을 목록에 넣을지 정할 때 가진 숫자가
  "전체 CER 0.48%p 악화"뿐이어서, **이득이 0인지 손해가 큰지 구분할 수 없었다.**
  결국 그 구간 오디오를 직접 세 조건으로 돌려보고 나서야(용어 없이도 맞힘) 판단할 수
  있었다. B-WER/U-WER을 나눠 쟀으면 그 한 번의 측정으로 끝났을 일이다.

한국어에서의 처리:
  조사가 붙어 용어가 단독 어절로 나오는 일이 드물다("온보딩까지", "임베딩을").
  그래서 **어절 안에 용어가 부분 문자열로 들어 있으면 그 어절을 '용어 어절'로 본다**
  — evaluate_wer.term_stats와 같은 규약(공백 제거 후 부분 문자열)이다.

삽입 오류의 귀속:
  없는 말을 지어냈을 때, 그 단어가 용어면 B쪽, 아니면 U쪽에 센다. 표준 정의를 따른다.
  **목록에 있는 단어를 지어내는 것이 과도한 바이어싱의 전형적 증상**이라 이 구분이 중요하다.

사용법:
  python bias_wer.py rep.json --terms ../../backend/modules/stt/core/terms_context.txt
  python bias_wer.py rep_terms.json rep_noterms.json --terms <용어파일>   # 두 조건 비교
"""
import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from evaluate_wer import normalize  # noqa: E402
from compare_reports import boot_ci  # noqa: E402


def load_terms(path: str) -> list[str]:
    out = []
    for raw in open(os.path.expanduser(path), encoding="utf-8"):
        raw = raw.strip()
        if raw and not raw.startswith("#"):
            t = normalize(raw).replace(" ", "")
            if t:
                out.append(t)
    return out


def is_biased(token: str, terms: list[str]) -> bool:
    """어절 안에 용어가 들어 있으면 용어 어절로 본다(조사 부착 대응)."""
    return any(t in token for t in terms)


def align_ops(ref: list[str], hyp: list[str]) -> list[tuple[str, str | None, str | None]]:
    """편집 연산 목록을 돌려준다 — 오류를 용어/비용어로 귀속시키려면 거리만으론 부족하다."""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1,
                           dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    ops, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append(("cor" if ref[i - 1] == hyp[j - 1] else "sub", ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("del", ref[i - 1], None)); i -= 1
        else:
            ops.append(("ins", None, hyp[j - 1])); j -= 1
    return ops[::-1]


def score(details: list[dict], terms: list[str]):
    """건별 (B오류, B정답수, U오류, U정답수, 용어 환각 수)를 모은다."""
    be, bn, ue, un, halluc = [], [], [], [], 0
    for d in details:
        ref = normalize(d["reference"]).split()
        hyp = normalize(d.get("hypothesis") or "").split()
        b_err = b_n = u_err = u_n = 0
        for op, r, h in align_ops(ref, hyp):
            if op == "ins":
                if is_biased(h, terms):
                    b_err += 1
                    halluc += 1     # 정답에 없는데 용어를 지어냄 = 과도한 바이어싱 신호
                else:
                    u_err += 1
                continue
            if is_biased(r, terms):
                b_n += 1
                b_err += (op != "cor")
            else:
                u_n += 1
                u_err += (op != "cor")
        be.append(b_err); bn.append(b_n); ue.append(u_err); un.append(u_n)
    return (np.array(be), np.array(bn), np.array(ue), np.array(un), halluc)


def report(path: str, terms: list[str], rng, n_boot: int):
    with open(path, encoding="utf-8") as f:
        r = json.load(f)
    if not r.get("details"):
        raise SystemExit(f"❌ {path}: details가 없다")
    be, bn, ue, un, halluc = score(r["details"], terms)
    print(f"{os.path.basename(path)}  (용어 {'적용' if r.get('context') else '없음'})")
    if bn.sum() == 0:
        print("  ⚠️ 정답에 용어가 한 번도 안 나온다 — 이 평가셋으로는 **이득을 잴 수 없다.**")
        print("     목록 밖 부작용(U-WER)만 의미가 있다.")
    else:
        b, blo, bhi = boot_ci(be, bn, n_boot, rng)
        print(f"  B-WER {b*100:6.2f}%  [{blo*100:.2f}, {bhi*100:.2f}]   "
              f"(용어 어절 {bn.sum()}개)")
    u, ulo, uhi = boot_ci(ue, un, n_boot, rng)
    print(f"  U-WER {u*100:6.2f}%  [{ulo*100:.2f}, {uhi*100:.2f}]   (그 외 어절 {un.sum()}개)")
    if halluc:
        print(f"  ⚠️ 정답에 없는 용어를 지어낸 횟수: {halluc}회 — 과도한 바이어싱 신호")
    print()
    return be, bn, ue, un


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", help="리포트 json 1개 또는 2개(앞=용어 적용)")
    parser.add_argument("--terms", required=True, help="용어 목록 파일")
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    terms = load_terms(args.terms)
    rng = np.random.default_rng(args.seed)
    print("=" * 76)
    print(f"용어 {len(terms)}개 — {os.path.basename(args.terms)}")
    print("=" * 76)

    data = [report(p, terms, rng, args.resamples) for p in args.reports[:2]]
    if len(data) < 2:
        print("두 번째 리포트를 주면 용어 적용 전후를 짝지어 비교한다.")
        return

    (be_a, bn_a, ue_a, un_a), (be_b, bn_b, ue_b, un_b) = data
    if len(be_a) != len(be_b):
        raise SystemExit("❌ 건수가 다르다 — 같은 매니페스트로 만든 리포트여야 한다")

    idx = rng.integers(0, len(be_a), size=(args.resamples, len(be_a)))

    def delta(ea, na, eb, nb):
        point = ea.sum() / max(na.sum(), 1) - eb.sum() / max(nb.sum(), 1)
        d = (ea[idx].sum(axis=1) / np.maximum(na[idx].sum(axis=1), 1)
             - eb[idx].sum(axis=1) / np.maximum(nb[idx].sum(axis=1), 1))
        lo, hi = np.percentile(d, [2.5, 97.5])
        return point, float(lo), float(hi)

    print("=" * 76)
    print(f"차이 (앞 − 뒤) — 음수면 앞(용어 적용) 쪽이 낫다")
    print("=" * 76)
    if bn_a.sum() and bn_b.sum():
        p, lo, hi = delta(be_a, bn_a, be_b, bn_b)
        verdict = "이득 있음" if hi < 0 else ("해로움" if lo > 0 else "**차이 없음**")
        print(f"  B-WER {p*100:+6.2f}%p  [{lo*100:+.2f}, {hi*100:+.2f}]   → {verdict}")
    else:
        print("  B-WER  — 정답에 용어가 없어 측정 불가")
    p, lo, hi = delta(ue_a, un_a, ue_b, un_b)
    verdict = "부작용 있음" if lo > 0 else ("오히려 개선" if hi < 0 else "**부작용 없음**")
    print(f"  U-WER {p*100:+6.2f}%p  [{lo*100:+.2f}, {hi*100:+.2f}]   → {verdict}")
    print()
    print("판단 기준: B-WER이 내려가고 U-WER이 그대로면 채택. U-WER이 올라가면")
    print("           목록이 없는 말을 끌어오고 있다는 뜻이라 줄이거나 빼야 한다.")


if __name__ == "__main__":
    main()
