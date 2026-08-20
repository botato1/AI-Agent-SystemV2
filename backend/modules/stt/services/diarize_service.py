import asyncio
import random

import numpy as np
import torch
from pyannote.audio import Pipeline
from ..core.config import logger, MIN_SPEAKERS, MAX_SPEAKERS, DIARIZATION_SEED


def to_annotation(output):
    """
    pyannote 파이프라인 결과에서 Annotation을 꺼낸다.

    버전에 따라 Annotation을 그대로 주기도 하고 래퍼 객체(DiarizeOutput 등)로 감싸서
    주기도 한다. 감싼 걸 그대로 쓰면 itertracks가 없다고 터진다 — 실제로 검증 도구에서
    한 번 물렸다. 그래서 이 판단을 한 곳에 모아두고 호출부는 전부 이걸 쓴다.
    """
    for attr in ("speaker_diarization", "annotation"):
        if hasattr(output, attr):
            return getattr(output, attr)
    return output


def tracks_of(output) -> list[dict]:
    """파이프라인 결과를 [{start, end, speaker}] 리스트로."""
    return [
        {"start": round(turn.start, 2), "end": round(turn.end, 2), "speaker": speaker}
        for turn, _, speaker in to_annotation(output).itertracks(yield_label=True)
    ]


async def run_diarization(
    pipeline: Pipeline,
    audio_input,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> list:
    """
    pyannote로 화자 분리를 수행하고 [{start, end, speaker}] 리스트를 반환합니다.
    동기 함수를 쓰레드풀에서 돌려서 STT와 asyncio.gather로 병행 실행이 가능하게 합니다.

    audio_input: 파일 경로(str) 또는 {"waveform": torch.Tensor(1×N), "sample_rate": int} 딕셔너리.
    서버에 FFmpeg가 없으면 pyannote의 파일 디코딩(torchcodec)이 실패하므로,
    회의 후 재분석(C-4)처럼 이미 메모리에 오디오가 있는 경우엔 딕셔너리로 넘길 것.

    min/max_speakers: 회의별로 인원을 아는 경우(사전 등록 모드) 호출부가 좁혀줄 수 있음.
    범위가 좁을수록 클러스터링이 안정적이므로, 알 수 있으면 넘기는 편이 좋다.
    미지정 시 config 기본값 사용.
    """
    min_spk = MIN_SPEAKERS if min_speakers is None else min_speakers
    max_spk = MAX_SPEAKERS if max_speakers is None else max_speakers
    # 호출부가 인원을 잘못 넘겨 상한<하한이 되면 pyannote가 예외를 내므로 방어
    max_spk = max(max_spk, min_spk)

    def _diarize():
        # 화자 분리 직전에 난수를 고정한다.
        #
        # 왜 (2026-08-19): pyannote의 군집화가 무작위 초기화를 쓴다. 같은 오디오·같은
        # 설정으로 세 번 돌렸더니 cpCER이 **56.60 / 62.68 / 70.80%로 14.2%p 흩어졌다**
        # (회의 8b5f84b7). 조건을 비교하려는데 잡음이 조건 차이보다 커서, 그 회의의
        # A/B/C 비교(54.23 / 64.71 / 62.68)가 통째로 무의미해졌다.
        #
        # 흔들린 것은 오배정(0~3건)이고 미상은 11~12로 안정적이었다. 이승주가 경계선
        # (회의 내 자기 0.391 < 타인 0.597)에 있어서 그의 발화 2건이 어디로 붙느냐에
        # 따라 결과가 크게 움직인 것이다. 경계에 걸린 회의일수록 잡음이 커진다.
        #
        # 시드를 고정한다고 판정이 맞아지지는 않는다. 다만 **같은 입력에 같은 출력**이
        # 나와야 조건을 비교할 수 있다. 재현성은 정확도와 별개로 필요한 성질이다.
        random.seed(DIARIZATION_SEED)
        np.random.seed(DIARIZATION_SEED)
        torch.manual_seed(DIARIZATION_SEED)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(DIARIZATION_SEED)

        # ⛔ 2026-08-19: 시드 고정만으로는 재현이 안 됐다. 같은 세 번 실행에서
        # cpCER이 62.68% / 70.80%로 여전히 갈렸다(회의 8b5f84b7). 난수 생성기는
        # 고정됐어도 cuDNN/cuBLAS의 GPU 커널 자체가 스레드 스케줄링에 따라
        # 부동소수점 결과가 미세하게 달라질 수 있다 — 특히 컨볼루션의 리덕션 순서.
        # 경계선 케이스(이승주 자기 0.391 < 타인 0.597)는 그 미세한 차이가 판정을
        # 뒤집을 만큼 증폭된다.
        #
        # cuDNN을 확정 모드로 강제한다. 속도는 느려질 수 있다 — 정확도가 아니라
        # 재현성이 목적이므로 감수한다. warn_only=True인 이유: 확정 구현이 없는
        # 연산을 만나면 예외 대신 경고만 내고 넘어간다. False로 하면 화자 분리
        # 자체가 실패할 수 있다.
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True, warn_only=True)

        return tracks_of(pipeline(audio_input, min_speakers=min_spk, max_speakers=max_spk))

    logger.info(f"🚀 화자 분리(pyannote) 분석 시작... (화자 수 {min_spk}~{max_spk}명 가정)")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _diarize)
    logger.info(f"✅ 화자 분리 완료: {len(results)}개 구간")

    return results