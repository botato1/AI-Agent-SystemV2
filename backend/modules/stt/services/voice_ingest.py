import asyncio

import numpy as np

from ..core.config import logger, REALTIME_SAMPLE_RATE, WHISPER_LANGUAGE, FAST_BEAM_SIZE
from .speaker_id_service import LiveSpeakerIdentifier

MIN_ENROLL_SEC = 0.5  # 이보다 짧은 오디오는 목소리 지문을 뽑기엔 정보가 부족함


async def ingest_voice_sample(app_state, pcm16_bytes: bytes) -> tuple[str, np.ndarray]:
    """
    "안녕하세요 OOO입니다" 같은 짧은 등록용 발화(PCM16LE 16kHz mono)를 받아
    (인식된 텍스트, 화자 임베딩)을 반환. 회의별 등록(enroll)과 전역 프로필 등록(profiles)이
    같은 검증/전사/임베딩 흐름을 공유하기 위한 공용 함수.

    입력이 잘못됐으면 ValueError(사용자에게 보여줄 한국어 메시지)를 던짐.
    GPU 작업은 executor에서 실행 — async 핸들러에서 직접 돌리면 이벤트 루프가 멈춰
    진행 중인 다른 회의의 실시간 스트리밍까지 얼어붙기 때문.
    """
    if len(pcm16_bytes) % 2 != 0:
        raise ValueError("오디오 데이터가 손상됨 (PCM16은 짝수 바이트여야 함)")

    samples = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    duration_sec = round(len(samples) / REALTIME_SAMPLE_RATE, 2)
    if duration_sec < MIN_ENROLL_SEC:
        raise ValueError(f"오디오가 너무 짧음 ({duration_sec}s < {MIN_ENROLL_SEC}s). 다시 녹음해줘.")

    loop = asyncio.get_event_loop()
    fast_model = app_state.stt_model_fast

    def _run_stt() -> str:
        segments, _info = fast_model.transcribe(
            samples,
            language=WHISPER_LANGUAGE,
            beam_size=FAST_BEAM_SIZE,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    detected_text = await loop.run_in_executor(None, _run_stt)

    identifier = LiveSpeakerIdentifier(app_state.speaker_embedding_inference)  # 임베딩 추출만 사용
    embedding = await loop.run_in_executor(None, identifier.extract_embedding, samples)

    logger.info(f"🎙️ 등록 발화 수신: {duration_sec}s, 인식=\"{detected_text}\"")
    return detected_text, embedding
