"""
"짧은 창으로 화자를 직접 판정할 수 있는가"를 재는 실험.

배경:
  지금 재분석은 pyannote 클러스터링 결과에 이름을 붙이는 방식이라, 클러스터링이
  틀리면 같이 틀린다. 실측(5인 공용 마이크 회의)에서 pyannote가 이준오·이승주를
  한 클러스터로 묶어 15.9초를 모아도 최고 유사도가 0.37(엉뚱한 사람)이었다.

  그런데 우리는 **참석자가 누구인지, 목소리가 어떤지 이미 알고 있다.** 클러스터링에
  기대지 말고 짧은 창마다 등록 프로필과 직접 대조하면 클러스터링 실패에 종속되지 않는다.

  이 스크립트는 그 방식이 성립하는지만 확인한다 — 창이 짧으면 임베딩이 흔들려서
  판정이 안 될 수 있고, 그러면 방향 자체가 무의미하다. **만들기 전에 잰다.**

1차 실측 결과 (5인 회의, 창 1.5초):
  전체 1등 정확도 94%. **창 단위 판정은 성립한다.**

  그리고 진짜 원인이 드러났다 — 실패했던 세 명의 평균 유사도가
  이준오 0.360 / 이승주 0.302 / 김나연 0.286으로 **전부 0.4 미만**인데
  1등은 87~94% 맞힌다. 순위는 처음부터 맞았고, SPEAKER_MIN_ASSIGN_SIMILARITY=0.4가
  정답을 걷어내고 있었다.

  절대 문턱은 "누가 말할지 모를 때" 쓰는 기준이다. 참석자를 아는 회의에선
  "충분히 닮았나"가 아니라 "다섯 중 누가 제일 닮았나"를 물어야 한다.
  절대 점수는 프로필 품질에 따라 0.29~0.53으로 흩어지므로 공통 문턱이 성립하지 않는다.

  음량 정규화는 효과가 0이었다(소수점 셋째 자리까지 동일). 임베딩 모델이 내부에서
  이득을 정규화하므로 녹음 크기는 영향을 주지 않는다 — 음량 가설은 폐기.

2차에서 재는 것:
  절대 점수를 버리고 무엇으로 판단할지. 1등과 2등의 차이(margin)가 후보다.
  - margin 분포: 맞을 때와 틀릴 때가 갈리는지
  - 문턱별 정확도/적용률: 어디서 끊어야 오답만 걸러지는지
  - 이웃 창 다수결 평활화가 94%를 얼마나 끌어올리는지

사용법:
  python probe_window_speaker_id.py --meeting <회의ID> \
      --truth 이준오:41.3-50.5 이승주:52.6-60.5 김나연:61.1-70.0 문지수:24-40 가동현:88.6-98
"""
import argparse
import os
import sys

import numpy as np
import soundfile as sf

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend", "modules"))

from stt.core.config import MEETINGS_DIR, REALTIME_SAMPLE_RATE  # noqa: E402
from stt.services.profile_store import GlobalProfileStore  # noqa: E402
from stt.services.speaker_id_service import (  # noqa: E402
    LiveSpeakerIdentifier, load_speaker_embedding_inference,
)


def cosine(a, b) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def smooth(labels: list, width: int = 3) -> list:
    """이웃 창 다수결. 한 창이 흔들려도 앞뒤가 같으면 그쪽으로 되돌린다."""
    half = width // 2
    out = []
    for i in range(len(labels)):
        window = labels[max(0, i - half): i + half + 1]
        out.append(max(set(window), key=window.count))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meeting", required=True)
    parser.add_argument("--audio", default="audio.wav")
    parser.add_argument("--truth", nargs="+", required=True,
                        help="정답 구간 '이름:시작-끝' (초)")
    parser.add_argument("--window", type=float, default=1.5, help="창 길이(초)")
    parser.add_argument("--hop", type=float, default=0.5, help="창 이동(초)")
    args = parser.parse_args()

    path = os.path.join(MEETINGS_DIR, args.meeting, args.audio)
    audio, sr = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    store = GlobalProfileStore()
    profiles = store.load(store.list_names())
    identifier = LiveSpeakerIdentifier(load_speaker_embedding_inference())

    win = int(args.window * sr)
    hop = int(args.hop * sr)

    print(f"창 {args.window}초 / 이동 {args.hop}초 / 등록 {len(profiles)}명\n")
    print(f"{'정답':8s}{'창수':>5s}{'1등정확':>8s}{'평활화후':>9s}"
          f"{'유사도':>8s}{'margin':>8s}{'오답margin':>11s}   오답으로 뽑힌 이름")
    print("-" * 84)

    rows = []          # (맞았나, margin) — 문턱 판단용
    total = hit = smoothed_hit = 0

    for spec in args.truth:
        name, span = spec.split(":")
        start, end = (float(x) for x in span.split("-"))
        seg = audio[int(start * sr):int(end * sr)]

        preds, scores, margins, bad_margins = [], [], [], []
        wrong: dict = {}
        for off in range(0, max(len(seg) - win + 1, 1), hop):
            clip = seg[off:off + win]
            if len(clip) < win // 2:
                break
            emb = identifier.extract_embedding(clip)
            ranked = sorted(((cosine(emb, v), k) for k, v in profiles.items()), reverse=True)
            top_score, top_name = ranked[0]
            # 2등과의 차이. 절대 점수는 프로필 품질 탓에 0.29~0.53으로 흩어져 공통
            # 문턱이 성립하지 않으므로, 대신 이걸로 판단할 수 있는지가 관건이다.
            margin = top_score - (ranked[1][0] if len(ranked) > 1 else 0.0)

            preds.append(top_name)
            scores.append(top_score)
            margins.append(margin)
            rows.append((top_name == name, margin))
            if top_name != name:
                wrong[top_name] = wrong.get(top_name, 0) + 1
                bad_margins.append(margin)

        if not preds:
            continue
        n = len(preds)
        h = sum(p == name for p in preds)
        sh = sum(p == name for p in smooth(preds))
        total += n
        hit += h
        smoothed_hit += sh

        wrong_str = ", ".join(f"{k} {v}" for k, v in sorted(wrong.items(), key=lambda x: -x[1])[:3])
        bad = f"{np.mean(bad_margins):11.3f}" if bad_margins else f"{'-':>11s}"
        print(f"{name:8s}{n:5d}{h/n*100:7.0f}%{sh/n*100:8.0f}%"
              f"{np.mean(scores):8.3f}{np.mean(margins):8.3f}{bad}   {wrong_str}")

    t = max(total, 1)
    print("-" * 84)
    print(f"{'전체':8s}{t:5d}{hit/t*100:7.0f}%{smoothed_hit/t*100:8.0f}%")

    # margin 문턱을 어디서 끊을지: 버리는 양 대비 정확도가 얼마나 오르는지 본다.
    print("\nmargin 문턱별 (문턱 미만은 '미상'으로 버림)")
    print(f"{'문턱':>6s}{'적용률':>8s}{'적용분 정확도':>14s}{'버린 것 중 오답':>17s}")
    for gate in (0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12):
        kept = [ok for ok, m in rows if m >= gate]
        dropped = [ok for ok, m in rows if m < gate]
        if not kept:
            continue
        drop_wrong = f"{sum(not ok for ok in dropped)}/{len(dropped)}" if dropped else "-"
        print(f"{gate:6.2f}{len(kept)/len(rows)*100:7.0f}%"
              f"{sum(kept)/len(kept)*100:13.0f}%{drop_wrong:>17s}")

    print("\n읽는 법:")
    print("  '버린 것 중 오답' 비율이 높을수록 문턱이 오답만 골라 버린다는 뜻 = 좋은 문턱")
    print("  적용률이 급격히 떨어지면 맞는 것까지 버리는 것이므로 그 앞에서 끊는다")


if __name__ == "__main__":
    main()
