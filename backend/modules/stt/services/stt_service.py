import asyncio
from faster_whisper import WhisperModel
from ..core.config import logger, WHISPER_BEAM_SIZE, WHISPER_LANGUAGE


async def run_whisper_stt(model: WhisperModel, wav_path: str, topic: str = "") -> list:
    """
    faster-whisper로 STT를 수행하고 [{start, end, text}] 리스트를 반환합니다.
    동기 함수(model.transcribe)를 쓰레드풀에서 돌려서 asyncio.gather와 병행 실행이 가능하게 합니다.
    (initial_prompt는 hotwords 제거 결정(2026-07-15)에 맞춰 실시간 경로와 함께 제거함 —
     전문용어 인식 개선은 파인튜닝으로 대체. topic 파라미터는 호출부 호환용으로만 유지.)
    """

    def _transcribe():
        segments, info = model.transcribe(
            wav_path,
            language=WHISPER_LANGUAGE,
            beam_size=WHISPER_BEAM_SIZE,
            vad_filter=True,                 # Silero VAD로 무음 구간 자동 스킵
            condition_on_previous_text=False, # 환각으로 인한 텍스트 무한 반복 방지
        )
        results = []
        for seg in segments:
            results.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            })
        return results, info

    logger.info("🚀 faster-whisper STT 분석 시작...")
    loop = asyncio.get_event_loop()
    results, info = await loop.run_in_executor(None, _transcribe)
    logger.info(f"✅ STT 완료: 감지 언어={info.language}, 세그먼트 수={len(results)}")

    return results