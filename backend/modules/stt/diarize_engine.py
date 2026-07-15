import sys
import json
import torch
import logging
import os
from pyannote.audio import Pipeline
from dotenv import load_dotenv

# 1. .env 파일에서 토큰 안전하게 불러오기
load_dotenv()

logging.getLogger("pyannote").setLevel(logging.CRITICAL)
logging.getLogger("torch").setLevel(logging.CRITICAL)

# 환경 변수에서 토큰 가져오기 (깃허브 노출 X)
TOKEN = os.getenv("HF_TOKEN")
if not TOKEN:
    sys.stderr.write("Error: HF_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.\n")
    sys.exit(1)

def run_diarization(wav_path):
    if not os.path.exists(wav_path):
        sys.stderr.write(f"Error: 파일을 찾을 수 없습니다 -> {wav_path}\n")
        sys.exit(1)

    # 2. 크로스 플랫폼 하드웨어 가속 지원 (Windows CUDA + Mac MPS)
    if torch.cuda.is_available():
        device = torch.device("cuda")  # Windows 팀원의 NVIDIA GPU
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")   # 준오 님의 Mac M5
    else:
        device = torch.device("cpu")   # GPU가 없는 컴퓨터
    
    try:
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=TOKEN)
        pipeline.to(device)
        
        diarization = pipeline(wav_path, min_speakers=2, max_speakers=5)
        
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
                "speaker": speaker
            })
            
        print(json.dumps(results))
        
    except Exception as e:
        sys.stderr.write(f"Error: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("Error: 파일 경로가 제공되지 않았습니다.\n")
        sys.exit(1)
    run_diarization(sys.argv[1])