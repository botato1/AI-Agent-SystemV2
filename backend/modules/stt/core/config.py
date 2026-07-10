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
# 실시간 회의 STT (2-pass) 설정
# Fast Pass: 청크 도착 즉시 저정밀 초안 → 지연 최소화
# Precise Pass: 곧이어 고정밀 확정본 → 오탐(false alarm) 방지
# ──────────────────────────────────────────
WHISPER_MODEL_FAST = "large-v3-turbo"
WHISPER_MODEL_PRECISE = WHISPER_MODEL_SIZE  # cuda면 large-v3, 아니면 turbo로 통일

FAST_BEAM_SIZE = 1        # greedy에 가깝게 → 최저 지연
PRECISE_BEAM_SIZE = WHISPER_BEAM_SIZE

# 신뢰도 게이팅 임계값 (이 기준 미달이면 모순 감지 엔진으로 안 보내고 보류)
CONF_AVG_LOGPROB_THRESHOLD = -1.0   # 이보다 낮으면(음수로 클수록 나쁨) 신뢰도 낮음
CONF_NO_SPEECH_THRESHOLD = 0.6      # 이보다 높으면 침묵/노이즈를 잘못 들었을 가능성

# VAD 기반 청크 분할 설정 (시간이 아니라 '말이 끊기는 지점' 기준으로 자름)
REALTIME_SAMPLE_RATE = 16000
REALTIME_MIN_CHUNK_SEC = 2      # 너무 짧은 청크는 흘려보내지 않음
REALTIME_MAX_CHUNK_SEC = 28     # 침묵이 안 와도 이 길이가 되면 강제로 자름
REALTIME_SILENCE_MS = 500       # 이만큼 침묵이 지속되면 발화 구간 종료로 판단

# Local Agreement 스트리밍 설정 — 발화자가 안 쉬고 계속 말해도
# 청크가 끝나기 전에 미리 텍스트를 흘려보내기 위한 파라미터
REALTIME_PARTIAL_INTERVAL_SEC = 1.0   # 이 주기로 버퍼 전체를 다시 훑어 잠정 텍스트 갱신
REALTIME_PARTIAL_MIN_SEC = 1.0        # 이보다 짧은 버퍼는 아직 잠정 전사 안 함

# ──────────────────────────────────────────
# pyannote 화자 분리 설정
# ──────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN")
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
MIN_SPEAKERS = 2
MAX_SPEAKERS = 5

# 실시간 화자 식별(임베딩 캐싱 방식) 설정
# 매 청크마다 전체 화자분리를 다시 도는 대신, 임베딩 유사도로 즉시 매칭
SPEAKER_EMBEDDING_MODEL = "pyannote/embedding"
SPEAKER_SIMILARITY_THRESHOLD = 0.75   # 이 이상 유사하면 같은 화자로 판단

# 로거 설정
logger = logging.getLogger("vigo_project")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

logger.info(f"⚙️  실행 디바이스: {DEVICE} / compute_type: {COMPUTE_TYPE} / 모델: {WHISPER_MODEL_SIZE}")