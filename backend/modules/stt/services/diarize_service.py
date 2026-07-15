import json
import subprocess
from modules.stt.core.config import PYTHON_EXEC, DIARIZE_SCRIPT, logger

def run_diarization(wav_path: str) -> list:
    """독립 프로세스로 화자 분리 엔진을 실행하고 JSON 배열을 반환합니다."""
    cmd = [PYTHON_EXEC, DIARIZE_SCRIPT, wav_path]
    
    try:
        logger.info("🚀 화자 분리 엔진 분석 시작...")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
        return json.loads(result.stdout)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ 화자 분리 엔진 실행 실패 (stderr): {e.stderr}")
        raise RuntimeError(f"화자 분리 엔진 에러: {e.stderr}")
    except json.JSONDecodeError:
        logger.error(f"❌ JSON 파싱 실패. 출력값: {result.stdout}")
        raise ValueError("화자 분리 엔진이 유효하지 않은 데이터를 반환했습니다.")