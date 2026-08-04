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

화자분리 결과에서 역산하지 않는 이유 (2026-08-04 실측 — 처음엔 그렇게 만들었다가 뒤집음):
  처음에는 "이미 돌린 화자분리 결과에서 구간이 겹치면 그게 겹침"이라고 봤다.
  모델을 하나 더 로드할 필요가 없어 보였다.

  **전부 오탐이었다.** 그 방식이 겹침이라고 표시한 11개 구간을 프레임 단위 모델로
  다시 재보니 **하나도 겹침이 아니었다**(전 구간 최대 1명). 화자분리의 턴 경계가
  살짝 겹친 것을 동시 발화로 읽고 있었던 것이다. 그 결과 이준오·가동현의 멀쩡한
  발언까지 "겹쳤다"고 표시됐다.

  화자분리는 클러스터링까지 끝난 결과라 "이 순간 몇 명이 말하는가"라는 정보가 이미
  뭉개져 있다. segmentation-3.0은 화자분리가 **내부적으로 쓰는** 모델이고 프레임마다
  동시 발화를 직접 예측한다. 클러스터링 전 단계라 그 정보가 살아 있다.
"""
import numpy as np

from ..core.config import (
    logger, OVERLAP_MIN_SEC, OVERLAP_SEGMENT_RATIO, OVERLAP_CLEAR_SPEAKER,
    REALTIME_SAMPLE_RATE,
)

_TIME_BIN_SEC = 0.1


def find_overlap_spans_from_audio(audio, inference, sample_rate: int = REALTIME_SAMPLE_RATE):
    """
    오디오를 segmentation 모델에 직접 물어 "2명 이상이 동시에 말한" 구간을 찾는다.

    inference: services/overlap_model.load_overlap_inference()가 만든 Inference.
               None이면 빈 목록(겹침 감지 없이 진행) — 모델을 못 써도 재분석은 돌아야 한다.

    ⚠️ skip_aggregation으로 청크별 예측을 받아야 한다. 이 모델은 "화자 조합"을 클래스로
       예측하는데 **조합 번호가 청크마다 다른 사람을 가리킨다.** 겹치는 청크의 확률을
       평균내면(기본 동작) 서로 다른 사람을 가리키는 값이 섞여 의미가 사라진다 —
       실측에서 사람이 말하는 구간이 '아무도 안 말함'으로 나왔다.
       반면 **인원수는 조합 순서와 무관**하므로, 청크별로 먼저 인원수를 뽑고 합친다.
    """
    if inference is None:
        return []

    import torch
    output = inference({
        "waveform": torch.from_numpy(np.asarray(audio, dtype=np.float32).reshape(1, -1)),
        "sample_rate": sample_rate,
    })
    data = np.asarray(output.data)
    if data.ndim != 3:
        logger.warning(f"⚠️ 겹침 모델 출력 형태가 예상과 다름 {data.shape} — 겹침 감지 생략")
        return []

    model = inference.model
    sizes = _powerset_cardinality(
        data.shape[-1], len(model.specifications.classes),
        getattr(model.specifications, "powerset_max_classes", 2),
    )
    if sizes is None:
        return []
    counts = sizes[data.argmax(axis=-1)]        # (청크수, 프레임수)

    chunks = output.sliding_window
    frames = model.receptive_field
    offsets = np.array([
        frames.start + frames.step * i + frames.duration / 2 for i in range(data.shape[1])
    ])

    total_bins = int(len(audio) / sample_rate / _TIME_BIN_SEC) + 2
    bin_max = np.zeros(total_bins)
    for c in range(data.shape[0]):
        idx = np.clip(((chunks[c].start + offsets) / _TIME_BIN_SEC).astype(int), 0, total_bins - 1)
        np.maximum.at(bin_max, idx, counts[c])

    # 2명 이상인 칸이 이어지는 구간을 뽑는다
    spans, start = [], None
    for i, value in enumerate(bin_max):
        if value >= 2 and start is None:
            start = i * _TIME_BIN_SEC
        elif value < 2 and start is not None:
            if i * _TIME_BIN_SEC - start >= OVERLAP_MIN_SEC:
                spans.append((start, i * _TIME_BIN_SEC))
            start = None
    return _merge(spans)


def _powerset_cardinality(num_classes: int, max_speakers: int, max_concurrent: int):
    """powerset 클래스 번호 → 동시 발화자 수. 매핑을 못 만들면 None(겹침 감지 생략)."""
    try:
        from pyannote.audio.utils.powerset import Powerset
        return np.asarray(Powerset(max_speakers, max_concurrent).mapping).sum(axis=1)
    except Exception:
        import itertools
        sizes = [
            len(combo)
            for k in range(max_concurrent + 1)
            for combo in itertools.combinations(range(max_speakers), k)
        ]
        if len(sizes) != num_classes:
            logger.warning(
                f"⚠️ powerset 클래스 수 불일치 (모델 {num_classes} vs 계산 {len(sizes)}) — 겹침 감지 생략"
            )
            return None
        return np.asarray(sizes)


def find_overlap_spans(tracks: list[dict], min_speakers: int = 2) -> list[tuple[float, float]]:
    """
    화자분리 구간 목록에서 min_speakers명 이상이 겹치는 시간대를 뽑는다.

    ⚠️ **운영 경로에서는 쓰지 않는다** — 오탐이 많다는 것이 실측으로 확인됐다.
       이 방식이 찾아낸 11개 구간을 프레임 모델로 재보니 하나도 겹침이 아니었다.
       화자분리의 턴 경계가 살짝 겹친 것을 동시 발화로 읽는다.
       겹침 판정은 find_overlap_spans_from_audio(모델에 직접 질의)를 쓸 것.

    두 방식을 비교하는 검증 도구(probe_overlap.py)를 위해 남겨둔다.
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
