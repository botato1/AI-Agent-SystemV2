import asyncio
from pyannote.audio import Pipeline
from ..core.config import logger, MIN_SPEAKERS, MAX_SPEAKERS


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
        return tracks_of(pipeline(audio_input, min_speakers=min_spk, max_speakers=max_spk))

    logger.info(f"🚀 화자 분리(pyannote) 분석 시작... (화자 수 {min_spk}~{max_spk}명 가정)")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _diarize)
    logger.info(f"✅ 화자 분리 완료: {len(results)}개 구간")

    return results