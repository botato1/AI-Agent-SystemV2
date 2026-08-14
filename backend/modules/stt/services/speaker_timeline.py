"""
등록된 참석자를 아는 회의에서, 오디오 전체에 대해 "언제 누가 말했는가"를 직접 만든다.

왜 화자분리(클러스터링) 결과에 이름을 붙이지 않는가:
  클러스터링은 **참석자가 누구인지 모른다는 전제**로 "몇 명이고 어디가 같은 사람인가"를
  추론한다. 그래서 클러스터링이 실패하면 이름 붙이기도 같이 실패한다. 실측(2026-08-03,
  정답 대본이 있는 5인 공용 마이크 회의)에서 pyannote가 이준오·이승주를 한 클러스터로
  묶었고, 그 15.9초를 전부 모아도 최고 유사도가 0.37(엉뚱한 사람)이었다.

  하지만 우리는 참석자가 누구인지, 목소리가 어떤지 **이미 알고 있다.** 그 정보를 쓰면
  클러스터링에 종속되지 않는다 — 짧은 창으로 오디오를 훑으며 매 순간 등록 프로필과
  직접 대조하면 된다. 같은 회의에서 이 방식의 창 단위 1등 정확도는 94%였다.

왜 절대 유사도 문턱을 쓰지 않는가 (이게 원래 실패의 진짜 원인이었다):
  실패했던 세 명의 평균 유사도는 이준오 0.360 / 이승주 0.302 / 김나연 0.286으로
  전부 하한(0.4) 미만인데, **1등은 87~94% 맞혔다.** 순위는 처음부터 맞았고 문턱이
  정답을 걷어내고 있었다. 절대 점수는 프로필 품질에 따라 0.29~0.53으로 흩어지므로
  모두에게 같은 문턱을 씌우는 것 자체가 성립하지 않는다.

  절대 문턱은 "누가 말할지 모를 때" 쓰는 기준이다(등록 안 된 사람이 말할 수 있으니
  '충분히 닮았나'를 물어야 한다). 참석자를 아는 회의에서 물어야 할 것은
  **"다섯 중 누가 제일 닮았나"**다. 그래서 여기서는 순위로 판정하고,
  1등과 2등의 차이(margin)로만 걸러낸다.

margin이 하는 일:
  순위 판정은 **무조건 누군가를 지목한다.** 침묵·잡음·두 사람이 겹쳐 말한 구간에도
  이름이 붙는다는 뜻이다. margin은 그걸 막는 유일한 방어선이다.
  실측에서 오답 창의 margin은 0.028~0.078, 정답 창은 평균 0.086~0.244였다.

평활화가 하는 일:
  창 하나가 순간적으로 튀는 것을 앞뒤 창이 되돌린다. 실측 94% → 97%.

주의: 음량 정규화는 효과가 없다(실측에서 소수점 셋째 자리까지 동일). 임베딩 모델이
내부에서 이득을 정규화하므로 녹음이 작게 됐다는 사실 자체는 판정에 영향을 주지 않는다.
"""
import os

import numpy as np
from faster_whisper.vad import VadOptions, get_speech_timestamps

from ..core.config import (
    logger,
    REALTIME_SAMPLE_RATE,
    SPEAKER_WINDOW_SEC,
    SPEAKER_WINDOW_HOP_SEC,
    SPEAKER_SMOOTH_WIDTH,
)

# 이보다 짧은 발화 구간은 창 하나도 못 채우므로 통째로 판정한다.
# 그보다 더 짧으면 임베딩이 발음 내용에 휘둘려 판정을 포기한다.
_MIN_WINDOW_SEC = 1.0


def _smooth(labels: list, width: int) -> list:
    """이웃 창 다수결. 한 창이 흔들려도 앞뒤가 같으면 그쪽으로 되돌린다."""
    if width < 2 or len(labels) < 2:
        return labels
    half = width // 2
    return [
        max(set(w := labels[max(0, i - half): i + half + 1]), key=w.count)
        for i in range(len(labels))
    ]


class EnrolledSpeakerTimeline:
    """
    (시작, 끝, 이름) 구간 목록. 이름이 None인 구간은 "등록된 누구인지 판정 못 함"이다.

    시간 겹침으로 조회하므로, 전사 세그먼트가 어떻게 잘렸든(화자분리 턴이든 30초 창이든)
    그 구간에서 제일 오래 말한 사람을 돌려줄 수 있다.
    """

    def __init__(self, slots: list[tuple[float, float, str | None]]):
        self.slots = slots

    def speaker_of(self, start: float, end: float) -> str | None:
        """구간 [start, end)에서 가장 오래 말한 등록자. 판정된 구간이 없으면 None."""
        by_name: dict[str, float] = {}
        for slot_start, slot_end, name in self.slots:
            if name is None or slot_end <= start:
                continue
            if slot_start >= end:
                break        # slots는 시간순이라 더 볼 필요 없음
            overlap = min(slot_end, end) - max(slot_start, start)
            if overlap > 0:
                by_name[name] = by_name.get(name, 0.0) + overlap
        if not by_name:
            return None
        return max(by_name.items(), key=lambda kv: kv[1])[0]

    def runs_in(self, start: float, end: float) -> list[tuple[float, float, str | None]]:
        """구간 안의 슬롯을 같은 이름끼리 이어붙여 (시작, 끝, 이름) 목록으로."""
        runs: list[list] = []
        for slot_start, slot_end, name in self.slots:
            if slot_end <= start:
                continue
            if slot_start >= end:
                break
            piece = (max(slot_start, start), min(slot_end, end), name)
            if runs and runs[-1][2] == name:
                runs[-1][1] = piece[1]
            else:
                runs.append([piece[0], piece[1], name])
        return [(a, b, n) for a, b, n in runs]

    def summary(self) -> str:
        totals: dict[str, float] = {}
        for start, end, name in self.slots:
            key = name or "미상"
            totals[key] = totals.get(key, 0.0) + (end - start)
        return ", ".join(f"{k} {v:.0f}초" for k, v in sorted(totals.items(), key=lambda kv: -kv[1]))


def build_speaker_timeline(
    audio: np.ndarray,
    profiles: dict[str, np.ndarray],
    inference,
    sample_rate: int = REALTIME_SAMPLE_RATE,
) -> EnrolledSpeakerTimeline:
    """
    오디오 전체를 짧은 창으로 훑어 화자 타임라인을 만든다.

    발화 구간(VAD)만 훑는다 — 침묵을 판정할 이유가 없고, 침묵에도 순위 판정은
    누군가를 지목하기 때문에 미리 빼는 편이 안전하다.
    """
    from .speaker_id_service import LiveSpeakerIdentifier

    identifier = LiveSpeakerIdentifier(inference, initial_profiles=profiles)
    win = int(SPEAKER_WINDOW_SEC * sample_rate)
    hop = int(SPEAKER_WINDOW_HOP_SEC * sample_rate)
    min_len = int(_MIN_WINDOW_SEC * sample_rate)

    spans = get_speech_timestamps(
        audio, VadOptions(min_silence_duration_ms=300), sampling_rate=sample_rate
    )
    slots: list[tuple[float, float, str | None]] = []
    dropped = 0

    for span in spans:
        span_start, span_end = span["start"], span["end"]
        if span_end - span_start < min_len:
            continue     # 창 하나도 못 채우는 짧은 조각 — 판정 포기(인접 구간이 덮는다)

        # 창 시작 위치들. 구간이 창보다 짧으면 구간 하나를 통째로 한 창으로 본다.
        offsets = (
            list(range(span_start, span_end - win + 1, hop))
            if span_end - span_start >= win else [span_start]
        )

        labels, bounds = [], []
        for off in offsets:
            clip = audio[off: min(off + win, span_end)]
            # 판정 규칙은 match_closed_set 한 곳에만 둔다 — 실시간 경로와 재분석이
            # 다른 기준으로 판정하면, 실시간에서 보이던 이름이 회의록에서 바뀐다.
            # margin 미달(잡음·겹침·화자 전환 경계)이나 바닥값 미달(명단 밖)이면 None.
            name, _nearest, _score, _margin = identifier.match_closed_set(
                identifier.extract_embedding(clip)
            )
            labels.append(name)
            if name is None:
                dropped += 1

            # 창은 서로 겹치므로, 각 창의 판정을 '중심 주변 hop 길이'에만 귀속시켜
            # 서로 겹치지 않는 타임라인을 만든다.
            center = (off + min(off + win, span_end)) / 2
            bounds.append((center - hop / 2, center + hop / 2))

        for (slot_start, slot_end), name in zip(bounds, _smooth(labels, SPEAKER_SMOOTH_WIDTH)):
            slots.append((slot_start / sample_rate, slot_end / sample_rate, name))

    slots.sort(key=lambda s: s[0])
    timeline = EnrolledSpeakerTimeline(slots)
    logger.info(
        f"🕐 화자 타임라인: 창 {len(slots)}개 (판정 실패 {dropped}개) — {timeline.summary()}"
    )
    return timeline


# 턴을 쪼갤 때, 이보다 짧게 말한 사람은 경계로 치지 않는다.
# 짧은 맞장구까지 경계로 삼으면 회의록이 조각으로 부서지고 전사 호출만 늘어난다.
#
# ⚠️ 이 값은 "맞장구가 긴 발언을 쪼개는 걸 막자"는 목적으로 정해졌다. 그런데 제품이
# 모순 감지라면 우선순위가 정반대다 — "네 그렇게 하죠"와 "아니요 그건 아닌데요"가
# 둘 다 1~2초짜리이고, 의사결정이 일어나는 자리가 바로 거기다. 실측(2026-08-13,
# 회의 ba8f38c4)에서 짧은 발언 7건이 자기 세그먼트를 잃고 옆 사람 발언에 흡수돼
# **다른 사람 이름으로 기록**됐다. 사라지는 것보다 나쁘다 — 같은 사람이 자기 말을
# 뒤집은 것처럼 보인다.
#
# 값을 바꿔가며 재보려고 환경변수로 뺐다(기본값은 종전과 동일).
# 함께 볼 것: SPEAKER_WINDOW_SEC(1.5), SPEAKER_SMOOTH_WIDTH(3) —
# 3창 다수결은 약 2.5초보다 짧은 발언을 지운다.
_MIN_SUBTURN_SEC = float(os.getenv("SPEAKER_MIN_SUBTURN_SEC", "1.0"))

# 미상 구간을 화자 경계로 인정할지. 기본값은 종전 동작(끔) — 4개 회의 cpCER로
# 검증한 뒤에 바꾼다. split_turns_by_timeline의 주석에 근거가 있다.
SPEAKER_UNKNOWN_AS_BOUNDARY = os.getenv(
    "SPEAKER_UNKNOWN_AS_BOUNDARY", "0").strip().lower() not in ("0", "false", "no")


def split_turns_by_timeline(
    turns: list[dict], timeline: EnrolledSpeakerTimeline,
    min_subturn_sec: float = _MIN_SUBTURN_SEC,
) -> list[dict]:
    """
    화자분리 턴 하나에 여러 사람이 들어 있으면 **전사하기 전에** 쪼갠다.

    왜 전사 전인가 (이게 핵심이다):
      지금까지는 화자분리 턴 단위로 전사한 뒤 이름을 붙였다. 그런데 화자가 빠르게
      교대하면 두 사람이 한 턴에 묶이고, **전사가 이미 뭉쳐진 뒤라 손쓸 수 없다.**
      타임라인은 "더 오래 말한 쪽"으로 통째로 귀속시킬 수밖에 없고, 앞뒤 절반이
      남의 이름을 달게 된다.

      실측(대본 대조): 이승주의 "넵넵 좋습니다"가 김나연 세그먼트에, 가동현의
      "네 좋습니다"가 문지수 세그먼트에 섞여 들어갔다. 팀에서도 같은 유형이
      제보됐다("빠른 화자 교대 시 한쪽으로 잘못 귀속됨").

      타임라인은 0.5초 해상도라 **화자분리보다 경계를 세밀하게 안다.** 그 정보로
      먼저 턴을 나누면, 전사 자체가 화자별로 분리돼 나온다.

    경계는 두 사람의 발화 사이 중간 지점으로 잡는다 — 타임라인 슬롯은 0.5초 단위라
    정확한 전환 시점을 모르고, 중간이 가장 오차가 적다.
    """
    result: list[dict] = []
    split_count = 0

    for turn in turns:
        # 짧게 스친 사람은 경계로 치지 않는다(맞장구 하나로 회의록이 부서지면 안 된다)
        #
        # 미상(None) 구간을 경계로 칠지는 SPEAKER_UNKNOWN_AS_BOUNDARY가 정한다.
        #
        # 왜 선택지로 두는가 (2026-08-13~14 실측):
        #   미상을 버리면 그 구간이 옆 사람 세그먼트로 흡수돼 **남의 이름을 달게 된다.**
        #   회의 ba8f38c4에서 이승주의 1.7초 발언이 문지수 발언으로 기록됐고, 모순 감지
        #   입장에서는 같은 사람이 자기 말을 뒤집은 것처럼 보인다 — 이름이 없는 것보다 나쁘다.
        #
        #   유사도가 낮은 발화에 억지로 이름을 붙이려는 시도는 전부 실패했다(문턱 0.30/0.25/
        #   0.15, 점수 정규화, 회의 내 프로필 적응 — 넷 다 회의를 넓히니 기각). 남은 길은
        #   **미상으로 두되 흡수되지 않게 하는 것**이다.
        #
        #   다만 미상 구간이 실제로는 한 사람의 발화 중 판정만 실패한 지점일 수도 있어,
        #   그 경우 멀쩡한 턴이 셋으로 쪼개진다. 그래서 켜고 끄며 재보게 두었다.
        runs = [
            run for run in timeline.runs_in(turn["start"], turn["end"])
            if (run[2] is not None or SPEAKER_UNKNOWN_AS_BOUNDARY)
            and run[1] - run[0] >= min_subturn_sec
        ]
        # 걸러낸 뒤 같은 사람이 이어지면 하나로 되돌린다 — 안 그러면 "A···(짧은 맞장구)···A"를
        # A 두 조각으로 쪼개게 된다. 같은 사람을 둘로 나누는 건 아무 의미가 없다.
        merged_runs: list[tuple[float, float, str | None]] = []
        for run in runs:
            if merged_runs and merged_runs[-1][2] == run[2]:
                merged_runs[-1] = (merged_runs[-1][0], run[1], run[2])
            else:
                merged_runs.append(run)
        runs = merged_runs

        if len(runs) < 2:
            result.append(turn)
            continue

        # 턴 시작 ~ (발화들 사이 중간지점들) ~ 턴 끝
        edges = [turn["start"]]
        edges += [(a[1] + b[0]) / 2 for a, b in zip(runs, runs[1:])]
        edges.append(turn["end"])

        for start, end, run in zip(edges, edges[1:], runs):
            result.append({**turn, "start": round(start, 2), "end": round(end, 2),
                           "speaker": run[2]})
        split_count += 1

    if split_count:
        logger.info(
            f"🔪 화자 경계로 턴 분할: {split_count}개 턴 → {len(result) - len(turns) + split_count}개 "
            f"(빠른 화자 교대가 한 세그먼트로 뭉치는 것 방지)"
        )
    return result


def find_speaker_runs(
    audio: np.ndarray, identifier, sample_rate: int,
    window_sec: float, hop_sec: float, smooth_width: int,
) -> list[tuple[int, int, str | None]]:
    """
    **침묵 없이 이어지는 오디오** 안에서 화자가 바뀌는 지점을 찾는다.
    [(시작 샘플, 끝 샘플, 이름), ...] — 이름이 None이면 판정 못 한 구간.

    build_speaker_timeline과 원리는 같지만 쓰임이 다르다:
      - 저쪽은 회의 전체를 VAD 구간마다 훑어 타임라인을 만든다(재분석, 지연 제약 없음)
      - 이쪽은 **이미 잘라놓은 오디오 하나**를 훑는다(실시간, 창 수가 곧 지연이다)

    왜 필요한가: 실시간은 침묵을 찾아 청크를 나누는데, 두 사람이 쉼 없이 주고받으면
    나눌 침묵이 없다. 그러면 질문과 답이 한 사람 발언으로 묶여 자막에 틀린 이름이 뜬다
    (팀 제보: "네, 제가 이번 주 안으로 반영해 볼게요. 감사합니다. 오늘은 여기까지 할게요."가
     한 사람으로 묶임 — 앞은 김나연, 뒤는 문지수였다).

    ⚠️ 실시간은 미래를 못 본다. 말이 끝나기 전에는 한 사람인지 두 사람인지 알 수 없는
       경우가 있어 재분석만큼 정확할 수 없다 — 재분석이 나중에 교정한다.
    """
    win, hop = int(window_sec * sample_rate), int(hop_sec * sample_rate)
    if len(audio) < win * 2:
        return [(0, len(audio), None)]      # 창 두 개도 안 나오면 나눌 근거가 없다

    labels, centers = [], []
    for off in range(0, len(audio) - win + 1, hop):
        name, _nearest, _score, _margin = identifier.match_closed_set(
            identifier.extract_embedding(audio[off:off + win])
        )
        labels.append(name)
        centers.append(off + win // 2)

    labels = _smooth(labels, smooth_width)

    # 같은 이름이 이어지는 구간을 하나로 묶는다. 경계는 두 창 중심의 중간 —
    # 창이 hop만큼 겹쳐 있어 정확한 전환 시점을 모르므로 중간이 오차가 가장 적다.
    runs: list[tuple[int, int, str | None]] = []
    start = 0
    for i in range(1, len(labels)):
        if labels[i] == labels[i - 1]:
            continue
        boundary = (centers[i - 1] + centers[i]) // 2
        runs.append((start, boundary, labels[i - 1]))
        start = boundary
    runs.append((start, len(audio), labels[-1]))
    return runs
