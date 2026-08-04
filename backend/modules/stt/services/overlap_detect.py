"""
두 사람 이상이 동시에 말한 구간을 찾아낸다.

왜 필요한가 (2026-08-04 실측):
  정답 대본이 있는 5인 회의에서 "네 좋습니다"를 **전원이 동시에** 말한 줄이 있는데,
  화자 판정이 이승주 한 사람으로 찍었다. 순위 판정은 무조건 누군가를 지목하기 때문이다.

  이건 문턱을 조정해서 풀 문제가 아니다. **겹친 목소리에서 한 명을 고르는 것 자체가
  틀린 답**이다. 정답이 "여러 명"인 질문에 한 명으로 답하면 무조건 틀린다.
  그럴 땐 "여러 명이 말했다"고 말하는 것이 정확한 답이다.

  틀린 이름이 붙으면 모순 감지가 엉뚱한 사람의 발언으로 판단한다. 미상이나 '여러 명'은
  회의록에서 사람이 고칠 수 있다 — 우리가 계속 지켜온 기준과 같다.

왜 새 모델을 안 쓰는가:
  pyannote에 겹침 전용 감지 모델이 따로 있지만, **이미 돌린 화자분리 결과에 답이 들어
  있다.** 화자분리는 구간마다 화자를 붙이는데, 서로 다른 화자의 구간이 시간상 겹치면
  그게 곧 겹쳐 말한 구간이다. 모델을 하나 더 로드할 이유가 없다(메모리·시작 시간).
"""
from ..core.config import (
    logger, OVERLAP_MIN_SEC, OVERLAP_SEGMENT_RATIO, OVERLAP_CLEAR_SPEAKER,
)


def find_overlap_spans(tracks: list[dict], min_speakers: int = 2) -> list[tuple[float, float]]:
    """
    화자분리 구간 목록에서 min_speakers명 이상이 동시에 말한 시간대를 뽑는다.

    스윕 라인: 모든 구간의 시작/끝을 시간순으로 훑으며 '지금 말하고 있는 화자 수'를 센다.

    **몇 명부터를 겹침으로 볼지가 중요하다** (2026-08-04 실측):
      2명 기준으로 잡으면 "한 사람이 말하는 중에 누가 짧게 맞장구친" 구간까지 전부
      걸린다. 그런 구간은 주된 화자가 명확해서 이름을 지우면 손해다 — 실측에서
      오배정 1개를 고치려다 맞는 이름 6개를 잃었다(이준오 "시연 전에", 가동현 발언 등).
      정말로 한 명을 고를 수 없는 것은 여러 명이 한꺼번에 말한 경우다.
    """
    events: list[tuple[float, int, str]] = []
    for track in tracks:
        speaker = track.get("speaker")
        if speaker is None or track["end"] <= track["start"]:
            continue
        events.append((track["start"], 1, speaker))
        events.append((track["end"], -1, speaker))
    if not events:
        return []

    # 같은 시각이면 끝(-1)을 먼저 처리한다 — 맞닿은 구간(A가 끝나는 순간 B가 시작)을
    # 겹침으로 세지 않기 위해서다.
    events.sort(key=lambda e: (e[0], e[1]))

    spans: list[tuple[float, float]] = []
    active: dict[str, int] = {}
    overlap_start: float | None = None

    for time, delta, speaker in events:
        active[speaker] = active.get(speaker, 0) + delta
        if active[speaker] <= 0:
            active.pop(speaker, None)

        if len(active) >= min_speakers and overlap_start is None:
            overlap_start = time
        elif len(active) < min_speakers and overlap_start is not None:
            if time - overlap_start >= OVERLAP_MIN_SEC:
                spans.append((overlap_start, time))
            overlap_start = None

    return _merge(spans)


def _merge(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """맞붙은 겹침 구간을 하나로 — 짧은 틈으로 갈라져 있으면 다루기만 번거롭다."""
    merged: list[tuple[float, float]] = []
    for start, end in sorted(spans):
        if merged and start - merged[-1][1] <= OVERLAP_MIN_SEC:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def overlap_ratio(start: float, end: float, spans: list[tuple[float, float]]) -> float:
    """구간 [start, end) 중 겹침 구간이 차지하는 비율."""
    duration = end - start
    if duration <= 0 or not spans:
        return 0.0
    covered = 0.0
    for span_start, span_end in spans:
        if span_end <= start:
            continue
        if span_start >= end:
            break
        covered += min(span_end, end) - max(span_start, start)
    return covered / duration


def concurrent_speakers(tracks: list[dict], start: float, end: float) -> int:
    """구간 [start, end)에서 동시에 말한 최대 화자 수 — 문턱을 정하기 위한 측정용."""
    peak = 0
    for time in sorted({t["start"] for t in tracks} | {t["end"] for t in tracks}):
        if not (start <= time < end):
            continue
        count = len({
            t["speaker"] for t in tracks
            if t["start"] <= time < t["end"] and t.get("speaker") is not None
        })
        peak = max(peak, count)
    return peak


def mark_overlapped_segments(segments: list[dict], spans: list[tuple[float, float]]) -> int:
    """
    발화 대부분이 겹침 구간인 세그먼트에 overlapped=True를 단다.

    **이름은 지우지 않는다**(OVERLAP_CLEAR_SPEAKER로 켤 수 있음). 원래는 "전원이
    동시에 말한 줄에서 한 명을 고르지 않게" 하려던 기능인데, 실측에서 지울 근거가
    안 나왔다 — pyannote는 전원이 답한 구간도 2명으로만 잡아서 맞장구와 구분되지
    않는다. 그 기준으로 지우면 오배정 1개를 고치고 맞는 이름 6개를 잃는다.

    표시만 달면 잃는 것이 없고, 모순 감지가 이 표시를 보고 해당 발언을 걸러내면
    틀린 이름이 실제로 해를 끼치는 지점은 막힌다.

    **부분적으로만 겹친 세그먼트는 건드리지 않는다.** 긴 발언 중간에 누가 "네" 하고
    끼어드는 건 흔한 일이고, 그 발언의 화자는 여전히 명확하다.

    스키마: overlapped 필드가 추가된다(기본적으로 speaker는 그대로).
    이 필드를 모르는 소비자는 지금까지와 똑같이 동작한다.
    """
    if not spans:
        return 0

    marked = 0
    for seg in segments:
        if overlap_ratio(seg["start"], seg["end"], spans) >= OVERLAP_SEGMENT_RATIO:
            seg["overlapped"] = True
            if OVERLAP_CLEAR_SPEAKER:
                seg["speaker"] = None
            marked += 1

    if marked:
        total = sum(end - start for start, end in spans)
        logger.info(
            f"🗣️🗣️ 겹쳐 말한 구간 {len(spans)}개({total:.0f}초) — 세그먼트 {marked}개에 표시"
            + (" (화자 이름 제거)" if OVERLAP_CLEAR_SPEAKER else "")
        )
    return marked
