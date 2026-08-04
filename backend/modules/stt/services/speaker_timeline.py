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
import numpy as np
from faster_whisper.vad import VadOptions, get_speech_timestamps

from ..core.config import (
    logger,
    REALTIME_SAMPLE_RATE,
    SPEAKER_WINDOW_SEC,
    SPEAKER_WINDOW_HOP_SEC,
    SPEAKER_MIN_MARGIN,
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
            embedding = identifier.extract_embedding(clip)
            ranked = identifier.rank_profiles(embedding)
            top_score, top_name = ranked[0]
            margin = top_score - (ranked[1][0] if len(ranked) > 1 else top_score)

            if margin < SPEAKER_MIN_MARGIN:
                # 1등과 2등이 비슷하면 등록된 누구의 목소리도 아닐 가능성이 크다
                # (잡음, 겹쳐 말한 구간, 화자 전환 경계).
                labels.append(None)
                dropped += 1
            else:
                labels.append(top_name)

            # 창은 서로 겹치므로, 각 창의 판정을 '중심 주변 hop 길이'에만 귀속시켜
            # 서로 겹치지 않는 타임라인을 만든다.
            center = (off + min(off + win, span_end)) / 2
            bounds.append((center - hop / 2, center + hop / 2))

        for (slot_start, slot_end), name in zip(bounds, _smooth(labels, SPEAKER_SMOOTH_WIDTH)):
            slots.append((slot_start / sample_rate, slot_end / sample_rate, name))

    slots.sort(key=lambda s: s[0])
    timeline = EnrolledSpeakerTimeline(slots)
    logger.info(
        f"🕐 화자 타임라인: 창 {len(slots)}개 (margin 미달 {dropped}개) — {timeline.summary()}"
    )
    return timeline
