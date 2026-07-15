import asyncio
from pyannote.audio import Pipeline
from ..core.config import logger, MIN_SPEAKERS, MAX_SPEAKERS


async def run_diarization(pipeline: Pipeline, audio_input) -> list:
    """
    pyannote로 화자 분리를 수행하고 [{start, end, speaker}] 리스트를 반환합니다.
    동기 함수를 쓰레드풀에서 돌려서 STT와 asyncio.gather로 병행 실행이 가능하게 합니다.

    audio_input: 파일 경로(str) 또는 {"waveform": torch.Tensor(1×N), "sample_rate": int} 딕셔너리.
    서버에 FFmpeg가 없으면 pyannote의 파일 디코딩(torchcodec)이 실패하므로,
    회의 후 재분석(C-4)처럼 이미 메모리에 오디오가 있는 경우엔 딕셔너리로 넘길 것.
    """

    def _diarize():
        diarization = pipeline(audio_input, min_speakers=MIN_SPEAKERS, max_speakers=MAX_SPEAKERS)

        if hasattr(diarization, "speaker_diarization"):
            annotation = diarization.speaker_diarization
        elif hasattr(diarization, "annotation"):
            annotation = diarization.annotation
        else:
            annotation = diarization

        results = []
        for turn, _, speaker in annotation.itertracks(yield_label=True):
            results.append({
                "start": round(turn.start, 2),
                "end": round(turn.end, 2),
                "speaker": speaker,
            })
        return results

    logger.info("🚀 화자 분리(pyannote) 분석 시작...")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _diarize)
    logger.info(f"✅ 화자 분리 완료: {len(results)}개 구간")

    return results