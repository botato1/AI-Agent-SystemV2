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


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n else v


def _extract_windows(
    audio: np.ndarray, identifier, sample_rate: int,
) -> tuple[list[np.ndarray], list[tuple[float, float]]]:
    """
    오디오를 VAD 발화 구간 안에서 겹치는 창으로 훑어 (임베딩 목록, 시간 경계 목록)을 만든다.

    build_speaker_timeline()과 build_speaker_timeline_clustered()가 창 추출 로직을
    공유하기 위해 뺐다 — 판정 방식(창별 독립 vs 묶음)만 다르고 "어디를 훑는가"는
    같아야 두 결과를 공정하게 비교할 수 있다.
    """
    win = int(SPEAKER_WINDOW_SEC * sample_rate)
    hop = int(SPEAKER_WINDOW_HOP_SEC * sample_rate)
    min_len = int(_MIN_WINDOW_SEC * sample_rate)

    spans = get_speech_timestamps(
        audio, VadOptions(min_silence_duration_ms=300), sampling_rate=sample_rate
    )
    embeddings: list[np.ndarray] = []
    bounds: list[tuple[float, float]] = []

    for span in spans:
        span_start, span_end = span["start"], span["end"]
        if span_end - span_start < min_len:
            continue     # 창 하나도 못 채우는 짧은 조각 — 판정 포기(인접 구간이 덮는다)

        offsets = (
            list(range(span_start, span_end - win + 1, hop))
            if span_end - span_start >= win else [span_start]
        )
        for off in offsets:
            clip = audio[off: min(off + win, span_end)]
            embeddings.append(_unit(identifier.extract_embedding(clip)))
            # 창은 서로 겹치므로, 각 창의 판정을 '중심 주변 hop 길이'에만 귀속시켜
            # 서로 겹치지 않는 타임라인을 만든다.
            center = (off + min(off + win, span_end)) / 2
            bounds.append(((center - hop / 2) / sample_rate, (center + hop / 2) / sample_rate))

    return embeddings, bounds


def build_speaker_timeline(
    audio: np.ndarray,
    profiles: dict[str, np.ndarray],
    inference,
    sample_rate: int = REALTIME_SAMPLE_RATE,
) -> EnrolledSpeakerTimeline:
    """
    오디오 전체를 짧은 창으로 훑어 화자 타임라인을 만든다.

    창 하나하나를 등록 프로필과 **독립적으로** 비교한다 — 이웃 3창 다수결
    (_smooth)로 순간적인 흔들림만 보정한다. 창 하나가 경계선(margin이 얇은
    지점)에 있으면 그 창 부근만 흔들리지만, 여러 창이 몰려서 같은 쪽으로
    틀리면 다수결로도 못 되돌린다 — build_speaker_timeline_clustered()의
    동기가 이것이다.

    발화 구간(VAD)만 훑는다 — 침묵을 판정할 이유가 없고, 침묵에도 순위 판정은
    누군가를 지목하기 때문에 미리 빼는 편이 안전하다.
    """
    from .speaker_id_service import LiveSpeakerIdentifier

    identifier = LiveSpeakerIdentifier(inference, initial_profiles=profiles)
    embeddings, bounds = _extract_windows(audio, identifier, sample_rate)

    labels: list[str | None] = []
    dropped = 0
    for emb in embeddings:
        # 판정 규칙은 match_closed_set 한 곳에만 둔다 — 실시간 경로와 재분석이
        # 다른 기준으로 판정하면, 실시간에서 보이던 이름이 회의록에서 바뀐다.
        # margin 미달(잡음·겹침·화자 전환 경계)이나 바닥값 미달(명단 밖)이면 None.
        name, _nearest, _score, _margin = identifier.match_closed_set(emb)
        labels.append(name)
        if name is None:
            dropped += 1

    slots = [
        (start, end, name)
        for (start, end), name in zip(bounds, _smooth(labels, SPEAKER_SMOOTH_WIDTH))
    ]
    slots.sort(key=lambda s: s[0])
    timeline = EnrolledSpeakerTimeline(slots)
    logger.info(
        f"🕐 화자 타임라인: 창 {len(slots)}개 (판정 실패 {dropped}개) — {timeline.summary()}"
    )
    return timeline


def _cluster_windows(
    embeddings: list[np.ndarray], max_clusters: int, merge_floor: float,
) -> list[int]:
    """
    회의 안의 창 임베딩들을 그리디 병합으로 묶는다. 반환은 창마다의 클러스터 번호.

    왜 k(클러스터 수)를 등록 인원수로 고정하지 않는가: 등록은 됐지만 한 마디도
    안 한 참석자가 있을 수 있다(회의 후 재분석 흔한 케이스). k를 강제로 맞추면
    실제로는 두 사람인데 셋으로 억지로 쪼갤 수 있다. 대신 **상한**(max_clusters
    = 등록 인원수)만 걸고, 남은 클러스터가 상한 이하로 줄어든 뒤에는 유사도가
    merge_floor보다 낮으면 더 합치지 않고 멈춘다 — 실제로 다른 목소리를
    억지로 합치는 것을 막는다.

    ⚠️ O(n^2) 쌍 비교를 병합마다 반복해 최악 O(n^3)이다. 창이 수백 개 수준
    (회의 30분~1시간)이면 몇 초~수십 초 안에 끝난다고 예상되나 **실측 안 됨**
    — 느리면 최근접 쌍 캐시로 최적화할 것.
    """
    n = len(embeddings)
    if n == 0:
        return []
    clusters: list[list[int]] = [[i] for i in range(n)]
    centroids: list[np.ndarray] = [e.copy() for e in embeddings]

    while len(clusters) > 1:
        best_sim, bi, bj = -2.0, -1, -1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                s = float(np.dot(centroids[i], centroids[j]))
                if s > best_sim:
                    best_sim, bi, bj = s, i, j
        if len(clusters) <= max_clusters and best_sim < merge_floor:
            break
        merged_idx = clusters[bi] + clusters[bj]
        merged_centroid = _unit(np.mean([embeddings[k] for k in merged_idx], axis=0))
        clusters[bi] = merged_idx
        centroids[bi] = merged_centroid
        del clusters[bj]
        del centroids[bj]

    labels = [0] * n
    for cluster_id, members in enumerate(clusters):
        for idx in members:
            labels[idx] = cluster_id
    return labels


# 클러스터를 병합할 최소 유사도. build_speaker_timeline의 SPEAKER_MIN_MARGIN(0.05)과는
# 다른 종류의 값이다 — 이건 "같은 사람인가"를 묻고, margin은 "등록자 중 누구인가"를 묻는다.
# 값 자체는 실측 없이 정한 초안이다 — probe_clustered_timeline.py(예정)로 검증 전에는
# 배포 기본값을 켜지 않는다(아래 SPEAKER_TIMELINE_CLUSTERED 참고).
_CLUSTER_MERGE_FLOOR = float(os.getenv("SPEAKER_CLUSTER_MERGE_FLOOR", "0.55"))

# 묶음 단위 판정(이 함수)을 실제로 쓸지. 기본값 꺼짐 — cpCER로 검증 전까지는
# build_speaker_timeline(창별 독립 판정)이 그대로 배포 경로다.
# 근거: NEXT.md #3 — "회의 내 프로필 판정 정확도 86~100% vs 등록 프로필 82~95%",
# 나쁜 발화 하나가 결과를 뒤집는 문제(8b5f84b7의 이승주 2발화, EXPERIMENTS.md).
SPEAKER_TIMELINE_CLUSTERED = os.getenv(
    "SPEAKER_TIMELINE_CLUSTERED", "0").strip().lower() not in ("0", "false", "no")


def build_speaker_timeline_clustered(
    audio: np.ndarray,
    profiles: dict[str, np.ndarray],
    inference,
    sample_rate: int = REALTIME_SAMPLE_RATE,
) -> EnrolledSpeakerTimeline:
    """
    build_speaker_timeline()의 대안 — 창을 독립적으로 판정하지 않고, 회의 안에서
    비슷한 목소리끼리 먼저 묶은 뒤(_cluster_windows) **묶음 전체의 평균 임베딩으로
    딱 한 번** 등록 프로필과 대조한다. 묶음에 속한 모든 창이 그 판정을 그대로 받는다.

    왜 (NEXT.md #3): 지금 방식(build_speaker_timeline)은 창 하나하나가 독립적으로
    등록 프로필과 경쟁하므로, 경계선에 있는 사람(자기 프로필과의 유사도가 낮은 사람)은
    창마다 판정이 흔들릴 수 있다 — 실측(2026-08-19, 8b5f84b7)에서 이승주의 발화 2건이
    어디로 붙느냐에 따라 cpCER이 56.60~70.80%로 14.2%p 흔들렸다. 묶음으로 먼저 뭉치면
    그 사람의 다른 발화 다수가 함께 평균에 들어가므로, 개별 창 하나의 노이즈가
    전체 판정을 못 뒤집는다.

    같은 이유로 명단 밖 오수락도 줄어들 것으로 기대한다 — 명단 밖 사람의 여러 발화가
    함께 묶이면 평균 임베딩이 등록자 누구와도 안 닮을 가능성이 개별 창보다 높다.
    **다만 이건 가설이다 — cpCER과 명단 밖 오수락을 실제로 재기 전에는 채택하지 않는다**
    (EXPERIMENTS.md의 "하지 말 것": EER만 보고 채택 금지, 반드시 우리 회의로 확인).

    ⚠️ 클러스터링이 실제 화자 수보다 적게 묶으면(다른 두 사람이 한 묶음이 되면) 그
    묶음 전체가 한 이름으로 뭉개진다 — 창별 판정보다 이 실패 모드가 새로 생긴다.
    _CLUSTER_MERGE_FLOOR가 너무 낮으면 이게 잦아진다. 반대로 너무 높으면 원래
    문제(창별 흔들림)가 그대로 남는다 — 이 값 자체도 스윕이 필요하다.
    """
    from .speaker_id_service import LiveSpeakerIdentifier

    identifier = LiveSpeakerIdentifier(inference, initial_profiles=profiles)
    embeddings, bounds = _extract_windows(audio, identifier, sample_rate)
    if not embeddings:
        return EnrolledSpeakerTimeline([])

    cluster_ids = _cluster_windows(
        embeddings, max_clusters=max(1, len(profiles)), merge_floor=_CLUSTER_MERGE_FLOOR,
    )
    n_clusters = len(set(cluster_ids))

    # 클러스터마다 평균 임베딩으로 딱 한 번 판정
    members_by_cluster: dict[int, list[int]] = {}
    for idx, cid in enumerate(cluster_ids):
        members_by_cluster.setdefault(cid, []).append(idx)

    cluster_name: dict[int, str | None] = {}
    dropped_clusters = 0
    for cid, members in members_by_cluster.items():
        centroid = _unit(np.mean([embeddings[i] for i in members], axis=0))
        name, _nearest, _score, _margin = identifier.match_closed_set(centroid)
        cluster_name[cid] = name
        if name is None:
            dropped_clusters += 1

    slots = [
        (start, end, cluster_name[cid])
        for (start, end), cid in zip(bounds, cluster_ids)
    ]
    slots.sort(key=lambda s: s[0])
    timeline = EnrolledSpeakerTimeline(slots)
    logger.info(
        f"🕐 화자 타임라인(묶음): 창 {len(slots)}개 → 묶음 {n_clusters}개 "
        f"(판정 실패 묶음 {dropped_clusters}/{n_clusters}) — {timeline.summary()}"
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

# 미상 구간을 화자 경계로 인정할지.
#
# ⛔ 2026-08-18 실측으로 **기각**됐다. 기본값 꺼짐을 유지할 것 —
#    켜면 오히려 나빠진다. 근거는 split_turns_by_timeline의 주석에 있다.
#    코드를 남겨둔 이유는 같은 발상이 다시 떠올랐을 때 재측정을 반복하지 않기 위해서다.
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
        #
        # ⛔ 결과 (2026-08-18, 하한 0.35 고정, 회의 2건):
        #
        #     회의                끔                        켬
        #     ba8f38c4   cpCER 28.82% 미상 7 오배정 1 → 40.35% 미상 6 오배정 5
        #     8b5f84b7   cpCER 54.23% 미상 17 오배정 0 → 66.74% 미상 16 오배정 7
        #
        #   **오배정이 줄기는커녕 늘었다.** 1→5, 0→7. 두 회의 방향이 같아 우연이 아니고,
        #   cpCER도 12%p씩 나빠졌다. 미상은 겨우 하나씩 줄었을 뿐이다.
        #
        #   왜 반대로 나왔나: 미상마다 턴을 쪼개니 세그먼트가 잘게 부서지고, 조각 하나하나가
        #   다시 화자 판정을 받으면서 **틀릴 기회가 늘어난다.** 전사도 문장이 토막 나 나빠진다.
        #   "틀린 이름 대신 이름 없음"을 얻으려 했는데 "틀린 이름을 더 많이" 얻었다.
        #
        #   이로써 화자 판정 개선 가설은 다섯 번째 기각이다
        #   (문턱 0.30/0.25/0.15, 점수 z정규화, 회의 내 프로필 적응, 그리고 이것).
        #   공통점: **판정 이후 단계를 만져서는 판정 실패를 되돌릴 수 없다.**
        #   남은 길은 임베딩 품질이나 등록/회의 조건 차이 쪽이다 — probe_profile_mismatch.py 참고.
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


def assign_unassigned_ids(
    segments: list[dict], audio: np.ndarray, sample_rate: int, inference,
) -> None:
    """
    화자 미상(speaker=None)인 세그먼트에 구분용 raw id를 붙인다 (제자리 수정).

    왜 (2026-08-21, 팀원 요청): 프론트가 "화자 A/B" 식으로 표시하려면 미상이어도
    최소한의 구분자가 필요한데, 지금까지는 미상이면 전부 None이라 같은 미상 화자가
    여러 번 말해도 구분이 안 됐다.

    반드시 **모든 이름 배정·턴 분할이 끝난 뒤(최종 세그먼트 단계)**에만 부른다.
    build_speaker_timeline이나 split_turns_by_timeline 내부에서 쓰면 안 된다 —
    그 로직들의 "None=미상"이라는 전제가 곳곳에 배어 있어(예: 짧은 미상 구간은
    이웃에 흡수, SPEAKER_UNKNOWN_AS_BOUNDARY 처리), None을 문자열로 바꾸면 그
    로직들이 연쇄적으로 다르게 동작한다 — 세밀하게 튜닝된 부분이라 회귀 위험이 크다
    (realtime_service.py, EXPERIMENTS.md 참고). 그래서 이 함수는 그 로직이 전부
    끝난 뒤 "표시용 라벨"만 덧붙이는 순수 후처리로 분리했다.

    LiveSpeakerIdentifier.label_unassigned()의 문턱(_UNASSIGNED_MERGE_THRESHOLD)이
    보수적으로 높게 잡혀 있어, 다른 사람을 합치는 위험보다 같은 사람을 여러 id로
    쪼개는 쪽을 택한다 — 2026-08-20 묶음 판정 실험의 결론 그대로.
    """
    from .speaker_id_service import LiveSpeakerIdentifier

    pool = LiveSpeakerIdentifier(inference)  # 프로필 없음 — label_unassigned 전용
    min_len = int(_MIN_WINDOW_SEC * sample_rate)

    for seg in segments:
        if seg.get("speaker") is not None:
            continue
        start = max(0, int(seg["start"] * sample_rate))
        end = min(len(audio), int(seg["end"] * sample_rate))
        if end - start < min_len:
            continue  # 너무 짧으면 임베딩이 불안정 — None으로 남겨둔다(기존 동작 유지)
        embedding = pool.extract_embedding(audio[start:end])
        seg["speaker"] = pool.label_unassigned(embedding, update_profile=True)
