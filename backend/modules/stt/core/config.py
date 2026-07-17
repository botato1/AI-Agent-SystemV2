import os
import platform
import logging
import torch
from dotenv import load_dotenv

load_dotenv()

# 기본 디렉토리 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 실시간 회의 기록 저장소 — 회의별로 오디오 원본(C-4 정밀 재분석용)과 전사 JSON을 보관
MEETINGS_DIR = os.path.join(BASE_DIR, "meetings")
os.makedirs(MEETINGS_DIR, exist_ok=True)

# 전역 목소리 프로필 저장소 — 최초 1회 등록한 목소리 지문을 영구 보관,
# 이후 회의에선 참석자 선택만으로 재사용 (매 회의 재등록 불필요)
VOICE_PROFILES_DIR = os.path.join(BASE_DIR, "voice_profiles")
os.makedirs(VOICE_PROFILES_DIR, exist_ok=True)

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
# STT 엔진 선택 (faster-whisper[ctranslate2] vs transformers)
# ctranslate2는 PyPI가 aarch64용 CUDA wheel을 배포하지 않아서, ARM 기반 GPU
# 서버(예: NVIDIA Grace-Blackwell 계열)에서는 GPU를 아예 못 씀. 이 경우
# 순수 PyTorch 기반인 transformers 엔진으로 자동 전환.
# 환경변수 STT_ENGINE=faster_whisper|transformers 로 수동 지정도 가능.
# ──────────────────────────────────────────
ARCH = platform.machine()
_env_engine = os.getenv("STT_ENGINE", "").strip().lower()
if _env_engine in ("faster_whisper", "transformers"):
    STT_ENGINE = _env_engine
elif ARCH == "aarch64" and DEVICE == "cuda":
    STT_ENGINE = "transformers"
else:
    STT_ENGINE = "faster_whisper"

# ──────────────────────────────────────────
# Whisper 모델 설정
# ──────────────────────────────────────────
WHISPER_LANGUAGE = "ko"
WHISPER_BEAM_SIZE = 10 if DEVICE == "cuda" else 5

if STT_ENGINE == "transformers":
    WHISPER_MODEL_SIZE = "openai/whisper-large-v3"
    WHISPER_MODEL_FAST = "openai/whisper-large-v3-turbo"
    WHISPER_MODEL_PRECISE = WHISPER_MODEL_SIZE if DEVICE == "cuda" else WHISPER_MODEL_FAST
else:
    WHISPER_MODEL_SIZE = "large-v3" if DEVICE == "cuda" else "large-v3-turbo"
    WHISPER_MODEL_FAST = "large-v3-turbo"
    WHISPER_MODEL_PRECISE = WHISPER_MODEL_SIZE  # cuda면 large-v3, 아니면 turbo로 통일

# ──────────────────────────────────────────
# 실시간 회의 STT 설정
# 잠정 텍스트(1초 주기 partial)는 Fast 모델(turbo, beam=1)이 담당하고,
# 청크 확정본은 Precise 모델(large-v3)이 담당하는 역할 분담 구조.
# (과거엔 확정 단계에서도 fast+precise를 병렬로 둘 다 돌렸지만, 두 결과를
#  같은 메시지에 담아 보내는 구조라 지연 이득이 없어서 fast pass는 제거함)
# ──────────────────────────────────────────
FAST_BEAM_SIZE = 1        # greedy에 가깝게 → 최저 지연 (partial 스트리밍용)
PRECISE_BEAM_SIZE = WHISPER_BEAM_SIZE

# 신뢰도 게이팅 임계값 (이 기준 미달이면 모순 감지 엔진으로 안 보내고 보류)
CONF_AVG_LOGPROB_THRESHOLD = -1.0   # 이보다 낮으면(음수로 클수록 나쁨) 신뢰도 낮음
CONF_NO_SPEECH_THRESHOLD = 0.6      # 이보다 높으면 침묵/노이즈를 잘못 들었을 가능성

# VAD 기반 청크 분할 설정 (시간이 아니라 '말이 끊기는 지점' 기준으로 자름)
REALTIME_SAMPLE_RATE = 16000
REALTIME_MIN_CHUNK_SEC = 2      # 너무 짧은 청크는 흘려보내지 않음
REALTIME_MAX_CHUNK_SEC = 28     # 침묵이 안 와도 이 길이가 되면 강제로 자름
REALTIME_SILENCE_MS = 500       # 이만큼 침묵이 지속되면 발화 구간 종료로 판단
REALTIME_FLUSH_CHECK_INTERVAL_SEC = 0.3  # VAD 기반 flush 판정 주기 (매 프레임 돌리면 CPU 낭비)
REALTIME_FLUSH_MIN_TAIL_SEC = 0.5        # 회의 종료 시 이보다 짧은 잔여 버퍼는 버림 (노이즈 수준)

# Local Agreement 스트리밍 설정 — 발화자가 안 쉬고 계속 말해도
# 청크가 끝나기 전에 미리 텍스트를 흘려보내기 위한 파라미터
REALTIME_PARTIAL_INTERVAL_SEC = 1.0   # 이 주기로 버퍼 전체를 다시 훑어 잠정 텍스트 갱신
REALTIME_PARTIAL_MIN_SEC = 1.0        # 이보다 짧은 버퍼는 아직 잠정 전사 안 함

# hotwords(initial_prompt)는 제거함 (2026-07-15) — 임의로 고른 단어 목록이라 근거가 약하고,
# 회의 주제가 바뀌면 안 맞을 수 있어서 대신 파인튜닝으로 정확도를 개선하기로 결정.
# 파인튜닝 준비/검증 전까지는 전문용어 인식률이 잠시 떨어질 수 있음 (트레이드오프 인지 후 결정).

# ──────────────────────────────────────────
# pyannote 화자 분리 설정
# ──────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN")
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
MIN_SPEAKERS = 1  # 2로 강제하면 혼자 말하는 테스트/회의에서 한 목소리를 억지로 둘로 쪼갬
MAX_SPEAKERS = 6  # 팀 인원(6명)에 맞춤

# 실시간 화자 식별(임베딩 캐싱 방식) 설정
# 매 청크마다 전체 화자분리를 다시 도는 대신, 임베딩 유사도로 즉시 매칭
#
# pyannote/embedding(범용 구형 모델)로 실측한 결과, 임계값을 0.75→0.5로 낮춰도
# 같은 화자가 매 청크(2~4초)마다 새 화자로 등록될 정도로 유사도가 불안정(0.33~0.57)했음.
# → 우리가 이미 쓰고 있는 화자분리 파이프라인(pyannote/speaker-diarization-3.1)이 내부적으로
#   쓰는 최신 임베딩 모델(wespeaker-voxceleb-resnet34-LM, ResNet 기반)로 교체해서 재실험.
SPEAKER_EMBEDDING_MODEL = "pyannote/wespeaker-voxceleb-resnet34-LM"
SPEAKER_SIMILARITY_THRESHOLD = 0.5   # 이 이상 유사하면 같은 화자로 판단. 모델 교체 후 재튜닝 필요할 수 있음

# 로거 설정
logger = logging.getLogger("vigo_project")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

logger.info(
    f"⚙️  실행 디바이스: {DEVICE} ({ARCH}) / compute_type: {COMPUTE_TYPE} / "
    f"엔진: {STT_ENGINE} / 모델: {WHISPER_MODEL_SIZE}"
)