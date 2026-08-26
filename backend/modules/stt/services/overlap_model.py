"""
겹침 감지용 segmentation 모델 로더.

화자분리(diarization-3.1)가 내부적으로 쓰는 것과 같은 모델이지만, 파이프라인 안에서는
클러스터링까지 끝난 결과만 밖으로 나와서 "이 순간 몇 명이 말하는가"를 꺼낼 수 없다.
그래서 같은 모델을 따로 한 번 더 올려 프레임 단위 예측을 직접 받는다.

이미 받아져 있는 모델이라(화자분리가 이걸 의존한다) 추가 다운로드나 권한이 필요 없다.
모델 자체가 작아 재분석에 얹는 비용도 작다.

실패하면 None을 돌려주고 겹침 감지 없이 진행한다 — 이 기능 때문에 재분석 전체가
멈추면 안 된다.
"""
import torch

from ..core.config import logger, HF_TOKEN, DEVICE, OVERLAP_MODEL

_inference = None
_load_failed = False


def load_overlap_inference():
    """무거운 로딩을 한 번만. 실패도 한 번만 기록하고 이후엔 조용히 None."""
    global _inference, _load_failed
    if _inference is not None or _load_failed:
        return _inference

    try:
        from pyannote.audio import Model, Inference
        model = Model.from_pretrained(OVERLAP_MODEL, use_auth_token=HF_TOKEN)
        # skip_aggregation이 핵심 — 이유는 overlap_detect.find_overlap_spans_from_audio 참고
        # (청크마다 화자 조합 번호가 다른 사람을 가리켜서, 확률을 평균내면 의미가 사라진다)
        inference = Inference(model, skip_aggregation=True)
        if DEVICE == "cuda":
            inference.to(torch.device("cuda"))
        _inference = inference
        logger.info(f"✅ 겹침 감지 모델 로드: {OVERLAP_MODEL}")
    except Exception as e:
        _load_failed = True
        logger.warning(f"⚠️ 겹침 감지 모델을 못 씀 — 겹침 표시 없이 진행: {e}")
    return _inference
