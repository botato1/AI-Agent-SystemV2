import asyncio
from faster_whisper import WhisperModel
from ..core.config import logger, WHISPER_BEAM_SIZE, WHISPER_LANGUAGE


async def run_whisper_stt(model: WhisperModel, wav_path: str, topic: str = "") -> list:
    """
    배치 업로드 경로의 STT. [{start, end, text, avg_logprob, no_speech_prob}]를 반환합니다.
    동기 함수(model.transcribe)를 쓰레드풀에서 돌려서 asyncio.gather와 병행 실행이 가능하게 합니다.

    신뢰도 신호(avg_logprob/no_speech_prob)를 반드시 함께 반환해야 합니다 — 호출부
    (pipeline.merge_transcript_with_diarization)가 팀 공통 스키마의 confident 필드를
    이 값으로 계산합니다. 예전엔 텍스트만 넘겨서 배치 결과에 confident가 아예
    빠져 있었습니다.

    model은 설정된 엔진(faster-whisper / transformers / Qwen)의 인스턴스이며 세 엔진이
    같은 transcribe 인터페이스를 제공합니다. topic 파라미터는 호출부 호환용으로만 유지
    (인식 힌트는 2026-07-15에 제거됨 — 지금은 Qwen 컨텍스트 바이어싱이 그 역할을 함).
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
                "avg_logprob": getattr(seg, "avg_logprob", None),
                "no_speech_prob": getattr(seg, "no_speech_prob", None),
            })
        return results, info

    logger.info("🚀 faster-whisper STT 분석 시작...")
    loop = asyncio.get_event_loop()
    results, info = await loop.run_in_executor(None, _transcribe)
    logger.info(f"✅ STT 완료: 감지 언어={info.language}, 세그먼트 수={len(results)}")

    return results