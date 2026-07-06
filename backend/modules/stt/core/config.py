import os
import logging
import torch
from dotenv import load_dotenv

load_dotenv()

# 기본 디렉토리 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ──────────────────────────────────────────
# 디바이스 자동 감지 (RTX 5090 서버 / 맥북 / CPU 폴백)
# ──────────────────────────────────────────
if torch.cuda.is_available():
    DEVICE = "cuda"
    COMPUTE_TYPE = "float16"   # RTX 5090 32GB VRAM 풀파워 모드
elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    DEVICE = "cpu"             # faster-whisper(CTranslate2)는 MPS 미지원, CPU로 폴백
    COMPUTE_TYPE = "int8"
else:
    DEVICE = "cpu"
    COMPUTE_TYPE = "int8"

# ──────────────────────────────────────────
# faster-whisper 모델 설정
# ──────────────────────────────────────────
WHISPER_MODEL_SIZE = "large-v3" if DEVICE == "cuda" else "large-v3-turbo"
WHISPER_BEAM_SIZE = 10 if DEVICE == "cuda" else 5
WHISPER_LANGUAGE = "ko"

# ──────────────────────────────────────────
# pyannote 화자 분리 설정
# ──────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN")
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
MIN_SPEAKERS = 2
MAX_SPEAKERS = 5

# 로거 설정
logger = logging.getLogger("vigo_project")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

logger.info(f"⚙️  실행 디바이스: {DEVICE} / compute_type: {COMPUTE_TYPE} / 모델: {WHISPER_MODEL_SIZE}")