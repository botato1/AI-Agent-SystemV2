import os
import json
import subprocess
from ..core.config import WHISPER_CLI, WHISPER_MODEL, logger

def run_whisper_stt(wav_path: str, topic: str = "") -> dict:
    """Whisper.cpp를 실행하고 추출된 텍스트/타임스탬프 데이터를 반환합니다."""
    output_prefix = wav_path.replace(".wav", "")
    json_path = f"{output_prefix}.json"
    
    cmd = [
        WHISPER_CLI, "-m", WHISPER_MODEL, "-f", wav_path, 
        "-l", "ko", "--prompt", f"비고 프로젝트, {topic}",
        # ⬇️ 추가된 핵심 성능 및 안전 파라미터 ⬇️
        "-t", "10",        # 🚀 스레드 8개 강제 할당 (M5 CPU 성능 100% 활용)
        "-et", "2.8",     # 🛡️ 환각 방어: 엔트로피 임계값을 높여 알 수 없는 소리를 텍스트로 우기는 현상 차단
        "-mc", "0",       # 🛡️ 환각 방어: 맥락 무한 반복 오류(루핑) 차단
        # -----------------------------------
        "-oj", "-of", output_prefix
    ]
    
    try:
        logger.info("🚀 Whisper STT 분석 시작...")
        subprocess.run(cmd, check=True)
        
        if not os.path.exists(json_path):
            raise FileNotFoundError("Whisper JSON 결과물이 생성되지 않았습니다.")
            
        with open(json_path, "r", encoding="utf-8") as f:
            whisper_data = json.load(f)
            
        return whisper_data, json_path
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Whisper 실행 실패: {e.stderr.decode()}")
        raise RuntimeError("Whisper STT 실행 중 오류가 발생했습니다.")