import asyncio
from .stt_service import run_whisper_stt
from .diarize_service import run_diarization
from ..core.config import logger


def merge_transcript_with_diarization(whisper_segments: list, diarization_tracks: list) -> list:
    """
    STT 세그먼트와 화자분리 트랙을 시간 겹침(overlap) 기준으로 병합.
    각 STT 세그먼트마다 시간상 가장 많이 겹치는 화자를 배정한다.
    배치 업로드 파이프라인과 회의 후 정밀 재분석(C-4)이 공유하는 핵심 로직.
    """
    final_result = []
    for seg in whisper_segments:
        start = seg["start"]
        end = seg["end"]
        text = seg["text"]

        best_speaker = "UNKNOWN"
        max_overlap = 0.0

        for track in diarization_tracks:
            overlap = min(end, track["end"]) - max(start, track["start"])
            if overlap > max_overlap:
                max_overlap = overlap
                best_speaker = track["speaker"]

        final_result.append({
            "start": start,
            "end": end,
            "speaker": best_speaker,
            "text": text,
            "user_edited": False
        })
    return final_result


async def process_audio_pipeline(stt_model, diarize_pipeline, wav_path: str, topic: str = "") -> list:
    """
    STT와 화자 분리를 '동시에' 실행하고 결과를 시간 겹침 기준으로 병합하는 메인 파이프라인.
    asyncio.gather로 두 GPU 작업을 병렬 실행해 전체 처리 시간을 단축합니다.
    """
    try:
        logger.info("⚡ STT + 화자 분리 병렬 실행 시작...")

        # 핵심 변경점: 순차 실행 → 동시 실행
        whisper_segments, diarization_tracks = await asyncio.gather(
            run_whisper_stt(stt_model, wav_path, topic),
            run_diarization(diarize_pipeline, wav_path),
        )

        logger.info("🔗 STT 데이터와 화자 분리 데이터 병합 중...")
        return merge_transcript_with_diarization(whisper_segments, diarization_tracks)

    except Exception as e:
        logger.error(f"❌ 파이프라인 실행 중 오류 발생: {str(e)}")
        raise e
