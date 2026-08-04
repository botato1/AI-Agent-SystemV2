"""
겹쳐 말한 구간을 화자별 음원으로 **분리**해서 각각 전사한다.

overlap_detect와 무엇이 다른가:
  overlap_detect는 "여기는 겹쳤으니 한 명으로 정하지 않겠다"고 **포기**하는 장치다.
  정직하지만 그 발언들은 회의록에서 화자를 잃는다.
  이쪽은 겹친 소리를 실제로 갈라서 **둘 다 살린다.**

원리:
  pyannote의 speech-separation 파이프라인(PixIT)은 화자분리와 음원분리를 함께 한다.
  입력 오디오 하나에서 화자 수만큼의 채널을 뽑아주며, 각 채널에는 그 사람 목소리만
  남는다. 그 채널을 각각 전사하면 겹친 구간에서도 두 발언을 모두 얻는다.

⚠️ 한계를 분명히 알고 쓸 것:
  - 두 명이 겹친 경우는 쓸 만하지만 **세 명 이상이면 급격히 나빠진다.**
  - 분리된 음성에는 인공적인 왜곡이 남아 전사 품질이 원본보다 떨어질 수 있다.
    그래서 **겹친 구간에만** 적용하고, 안 겹친 구간은 원본을 그대로 쓴다.
  - 무겁다. 실시간에는 못 쓰고 재분석(백그라운드)에서만 쓴다.
  - 마이크 하나에 섞인 소리를 완벽히 되돌리는 것은 물리적으로 불가능하다.
    개선이지 해결이 아니다.

모델이 없거나 로드에 실패하면 조용히 비활성으로 떨어진다 — 이 기능 때문에 재분석
전체가 실패하면 안 된다. 서버에서 쓸 수 있는지는 finetune/stt/probe_separation.py로 확인.
"""
import numpy as np
import torch

from ..core.config import (
    logger,
    HF_TOKEN,
    DEVICE,
    SEPARATION_MODEL,
    SEPARATION_MIN_ENERGY,
)

_pipeline = None
_load_failed = False


def load_separation_pipeline():
    """
    무거운 모델이라 한 번만 로드하고 재사용한다. 실패는 한 번만 기록하고
    이후엔 조용히 None을 준다 — 회의마다 같은 예외를 다시 던질 이유가 없다.
    """
    global _pipeline, _load_failed
    if _pipeline is not None or _load_failed:
        return _pipeline

    try:
        from pyannote.audio import Pipeline
        # Pipeline은 token=, Model은 use_auth_token= 으로 인자 이름이 다르다
        # (main.py의 화자분리 파이프라인 로드와 같은 형태여야 한다)
        pipeline = Pipeline.from_pretrained(SEPARATION_MODEL, token=HF_TOKEN)
        if pipeline is None:
            raise RuntimeError(
                "Pipeline.from_pretrained가 None을 반환 — "
                "모델 사용 조건에 동의했는지, HF_TOKEN이 유효한지 확인 필요"
            )
        if DEVICE == "cuda":
            pipeline.to(torch.device("cuda"))
        _pipeline = pipeline
        logger.info(f"✅ 음원 분리 모델 로드: {SEPARATION_MODEL}")
    except Exception as e:
        _load_failed = True
        logger.warning(f"⚠️ 음원 분리 모델을 못 씀 — 겹침 분리 없이 진행: {e}")
    return _pipeline


def separate_sources(
    audio: np.ndarray, sample_rate: int
) -> tuple[dict[str, np.ndarray], list[dict]] | None:
    """
    오디오를 화자별 채널로 분리한다.

    반환: ({화자라벨: 오디오}, 화자분리 구간 목록) 또는 None(사용 불가).
    분리 파이프라인이 화자분리도 같이 해주므로 그 결과를 함께 돌려준다 —
    분리된 채널이 어느 구간에서 활성인지 판단하는 데 쓴다.
    """
    pipeline = load_separation_pipeline()
    if pipeline is None:
        return None

    try:
        waveform = torch.from_numpy(audio.reshape(1, -1).astype(np.float32))
        diarization, sources = pipeline({"waveform": waveform, "sample_rate": sample_rate})
    except Exception:
        logger.exception("⚠️ 음원 분리 실패 — 겹침 분리 없이 진행")
        return None

    # sources.data 는 (샘플수, 화자수). 열 순서가 diarization의 화자 라벨 순서와 같다.
    labels = list(diarization.labels())
    data = np.asarray(sources.data)
    if data.ndim != 2 or data.shape[1] != len(labels):
        logger.warning(
            f"⚠️ 분리 결과 형태가 예상과 다름 (채널 {data.shape} vs 화자 {len(labels)}명) — 건너뜀"
        )
        return None

    channels = {label: data[:, i].astype(np.float32) for i, label in enumerate(labels)}
    tracks = [
        {"start": round(turn.start, 2), "end": round(turn.end, 2), "speaker": speaker}
        for turn, _, speaker in diarization.itertracks(yield_label=True)
    ]
    logger.info(f"🔀 음원 분리 완료: {len(channels)}개 채널")
    return channels, tracks


def active_channels(
    channels: dict[str, np.ndarray], start: float, end: float, sample_rate: int
) -> list[str]:
    """
    구간 [start, end)에서 실제로 소리가 있는 채널만 고른다.

    분리 모델은 화자 수만큼 채널을 항상 만들어내므로, 그 사람이 말하지 않은 구간의
    채널에는 거의 무음에 가까운 잔향만 남는다. 그걸 전사하면 헛것이 나온다.
    """
    active = []
    for label, channel in channels.items():
        clip = channel[int(start * sample_rate): int(end * sample_rate)]
        if len(clip) and float(np.sqrt((clip ** 2).mean())) >= SEPARATION_MIN_ENERGY:
            active.append(label)
    return active
