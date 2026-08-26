"""
두 평가 리포트의 차이가 **진짜인지 잡음인지** 부트스트랩으로 판정한다.

왜 필요한가 (2026-08-10, 문헌 검토에서 출발):
  지금까지 우리는 단일 측정값 두 개를 그냥 빼서 "0.48%p 나빠졌다"고 판단해왔다.
  그런데 CER은 표본에서 추정한 값이라 **표본이 바뀌면 흔들린다.** 우리 평가셋
  크기에서 그 흔들림이 얼마인지 모르는 채로 소수점 차이를 근거로 결정해온 것이다.

  실제로 하루에 세 번, 잡음 범위의 차이를 근거로 결론을 낼 뻔했다:
    - `온보딩` 용어 추가가 우리 녹음에서 0.48%p 악화 (40건 = 약 1,500자)
    - 같은 변경이 일반 음성에서 0.12%p 개선 (500건)
    - padding이 회의 하나에서 0.62%p 개선, 다른 하나에서 0.58%p 악화
  이 중 어느 것도 표본 크기를 고려하면 "차이 있음"이라고 말할 수 없다.

  ASR 논문은 두 시스템을 비교할 때 부트스트랩 신뢰구간이나 MAPSSWE 검정을 붙인다.
  (Liu et al., "Statistical Testing on ASR Performance via Blockwise Bootstrap",
   Interspeech 2020 — arxiv.org/abs/1912.09508)

측정 방식:
  발화(item) 단위로 복원추출해 CER을 다시 계산하기를 반복한다. **비율 추정량이므로
  건별 CER의 평균이 아니라 오류합/정답합으로 매번 다시 계산해야 한다** — 짧은 발화의
  CER이 과대 반영되는 것을 막기 위함.

  두 리포트를 주면 **같은 표본에서 짝지어(paired)** 차이를 잰다. 두 시스템이 같은
  발화에서 같이 어려워하는 경향이 있으므로, 짝짓지 않으면 차이의 불확실성이 부풀려진다.

⚠️ 한계: 발화 단위 복원추출은 **같은 화자의 발화들이 서로 얽혀 있는 것**을 무시한다.
   엄밀히는 화자 블록 단위로 뽑아야 하고(blockwise bootstrap), 그러면 구간이 지금보다
   넓어진다. 즉 여기서 "차이 없음"이 나오면 확실히 차이가 없고, "차이 있음"이 나와도
   경계에 가까우면 더 조심해야 한다.

사용법:
  python compare_reports.py today_qwen.json                    # 한 개 — CER과 신뢰구간
  python compare_reports.py today_qwen.json today_whisper.json # 두 개 — 차이 검정
"""
import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from evaluate_wer import normalize, edit_distance  # noqa: E402


def item_errors(details: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """리포트의 건별 reference/hypothesis에서 오류 수와 정답 길이를 다시 센다.

    저장된 cer/wer(비율)을 쓰지 않는 이유: 비율은 길이 정보를 잃어서 합칠 수 없다.
    reference는 저장 시점에 이미 태그 정규화가 끝난 값이라 그대로 쓰면 된다.
    """
    ce, cn, we, wn = [], [], [], []
    for d in details:
        ref, hyp = normalize(d["reference"]), normalize(d.get("hypothesis") or "")
        rw, hw = ref.split(), hyp.split()
        rc, hc = list(ref.replace(" ", "")), list(hyp.replace(" ", ""))
        ce.append(edit_distance(rc, hc)); cn.append(len(rc))
        we.append(edit_distance(rw, hw)); wn.append(len(rw))
    return np.array(ce), np.array(cn), np.array(we), np.array(wn)


def boot_ci(err: np.ndarray, ref: np.ndarray, n: int, rng) -> tuple[float, float, float]:
    """(추정값, 하한, 상한). 비율 추정량이라 매번 합을 다시 낸다."""
    point = err.sum() / max(ref.sum(), 1)
    idx = rng.integers(0, len(err), size=(n, len(err)))
    samples = err[idx].sum(axis=1) / np.maximum(ref[idx].sum(axis=1), 1)
    return point, float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def paired(err_a, ref_a, err_b, ref_b, n: int, rng) -> dict:
    """같은 표본에서 짝지어 A−B 차이의 분포를 낸다."""
    point = err_a.sum() / max(ref_a.sum(), 1) - err_b.sum() / max(ref_b.sum(), 1)
    idx = rng.integers(0, len(err_a), size=(n, len(err_a)))
    d = (err_a[idx].sum(axis=1) / np.maximum(ref_a[idx].sum(axis=1), 1)
         - err_b[idx].sum(axis=1) / np.maximum(ref_b[idx].sum(axis=1), 1))
    lo, hi = np.percentile(d, [2.5, 97.5])
    # 부호가 0을 넘는 비율 → 양측 p값(백분위 방식)
    p = 2 * min((d <= 0).mean(), (d >= 0).mean())
    return {"point": point, "lo": float(lo), "hi": float(hi), "p": float(min(p, 1.0))}


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        r = json.load(f)
    if not r.get("details"):
        raise SystemExit(f"❌ {path}: details가 없어 재계산할 수 없다 (옛 리포트 형식)")
    return r


def label(r: dict) -> str:
    model = str(r.get("model", "?")).split("/")[-1]
    return f"{model} (용어 {'O' if r.get('context') else '-'}, ITN {'O' if r.get('itn') else '-'})"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", help="리포트 json 1개 또는 2개")
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=0, help="재현 가능하게 고정")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    reports = [load(p) for p in args.reports[:2]]
    data = [item_errors(r["details"]) for r in reports]

    print("=" * 76)
    for path, r, (ce, cn, we, wn) in zip(args.reports, reports, data):
        cer, lo, hi = boot_ci(ce, cn, args.resamples, rng)
        wer, wlo, whi = boot_ci(we, wn, args.resamples, rng)
        print(f"{os.path.basename(path)}  —  {label(r)}")
        print(f"  발화 {len(ce)}건 / 정답 {cn.sum():,}자")
        print(f"  CER {cer*100:6.2f}%   95% 구간 [{lo*100:.2f}, {hi*100:.2f}]  (±{(hi-lo)/2*100:.2f}%p)")
        print(f"  WER {wer*100:6.2f}%   95% 구간 [{wlo*100:.2f}, {whi*100:.2f}]")
        print()

    if len(reports) < 2:
        ce, cn = data[0][0], data[0][1]
        _, lo, hi = boot_ci(ce, cn, args.resamples, rng)
        print("=" * 76)
        print(f"이 평가셋에서 **{(hi-lo)/2*100:.2f}%p보다 작은 차이는 구별할 수 없다.**")
        print("변경 전후를 비교하려면 리포트 두 개를 주면 짝지어 검정한다.")
        return

    if len(data[0][0]) != len(data[1][0]):
        raise SystemExit(f"❌ 건수가 다르다({len(data[0][0])} vs {len(data[1][0])}) — "
                         "같은 매니페스트로 만든 리포트여야 짝지어 비교할 수 있다")

    res = paired(data[0][0], data[0][1], data[1][0], data[1][1], args.resamples, rng)
    a, b = os.path.basename(args.reports[0]), os.path.basename(args.reports[1])
    print("=" * 76)
    print(f"차이 (앞 − 뒤) = {res['point']*100:+.2f}%p   "
          f"95% 구간 [{res['lo']*100:+.2f}, {res['hi']*100:+.2f}]   p = {res['p']:.3f}")
    print("=" * 76)
    if res["lo"] <= 0 <= res["hi"]:
        print("→ **차이 없음.** 신뢰구간이 0을 포함한다 — 이 표본으로는 두 시스템을")
        print("   구별할 수 없다. 측정값의 부호(어느 쪽이 낮은지)를 근거로 쓰지 말 것.")
        print(f"   구별하려면 표본을 늘리거나, 차이가 {max(abs(res['lo']), abs(res['hi']))*100:.2f}%p보다 커야 한다.")
    else:
        better = b if res["point"] > 0 else a
        print(f"→ **차이 있음** (p={res['p']:.3f}). {better} 쪽이 낮다.")
        print("   단 발화 단위 복원추출이라 화자 상관을 무시했다 — 경계에 가까우면 조심할 것.")


if __name__ == "__main__":
    main()
