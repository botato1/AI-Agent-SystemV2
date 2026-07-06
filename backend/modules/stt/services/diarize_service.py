import asyncio
from pyannote.audio import Pipeline
from ..core.config import logger, MIN_SPEAKERS, MAX_SPEAKERS


async def run_diarization(pipeline: Pipeline, wav_path: str) -> list:
    """
    pyannote로 화자 분리를 수행하고 [{start, end, speaker}] 리스트를 반환합니다.
    동기 함수를 쓰레드풀에서 돌려서 STT와 asyncio.gather로 병행 실행이 가능하게 합니다.
    """

    def _diarize():
        diarization = pipeline(wav_path, min_speakers=MIN_SPEAKERS, max_speakers=MAX_SPEAKERS)

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