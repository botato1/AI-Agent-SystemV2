from .stt_service import run_whisper_stt
from .diarize_service import run_diarization
from ..utils.file_handler import cleanup_files
from ..core.config import logger

def process_audio_pipeline(wav_path: str, topic: str = "") -> list:
    """STT와 화자 분리를 실행하고 데이터를 병합하는 메인 파이프라인"""
    json_path = None
    
    try:
        # 1. 두 개의 AI 엔진 각각 실행
        whisper_data, json_path = run_whisper_stt(wav_path, topic)
        diarization_tracks = run_diarization(wav_path)
        
        # 2. 데이터 병합 로직
        logger.info("🔗 STT 데이터와 화자 분리 데이터 병합 중...")
        final_result = []
        
        for item in whisper_data.get("transcription", []):
            start = item["offsets"]["from"] / 1000.0
            end = item["offsets"]["to"] / 1000.0
            text = item["text"].strip()
            
            best_speaker = "UNKNOWN"
            max_overlap = 0.0
            
            # 발화 구간 겹침(Overlap) 검사로 최적의 화자 찾기
            for track in diarization_tracks:
                overlap = min(end, track["end"]) - max(start, track["start"])
                if overlap > max_overlap:
                    max_overlap = overlap
                    best_speaker = track["speaker"]
            
            # 💡 개별 대사별로 user_edited 플래그 추가 (초기값 False)
            final_result.append({
                "start": round(start, 2), 
                "end": round(end, 2), 
                "speaker": best_speaker,
                "text": text,
                "user_edited": False
            })
            
        return final_result
        
    except Exception as e:
        logger.error(f"❌ 파이프라인 실행 중 오류 발생: {str(e)}")
        raise e