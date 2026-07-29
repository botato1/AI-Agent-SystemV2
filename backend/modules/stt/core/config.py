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
# 빔 크기 실측 (2026-07-27, AI Hub 회의 음성 held-out 500건 / v4 어댑터):
#   beam=10 → CER 0.1118, 2.72초/건   beam=5 → 0.1116, 2.30초/건
#   beam=3  → CER 0.1108, 2.19초/건   beam=1 → 0.1080, 1.73초/건
# 빔을 줄일수록 단조롭게 빨라지는데 정확도는 나빠지지 않았음(CER 차이는 19,197자 기준
# 표본오차 범위). 즉 기존 beam=10이 쓰던 계산량은 사실상 낭비였고, greedy가 1.57배 빠르다.
WHISPER_BEAM_SIZE = 1

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

# 실시간 확정 전사(final)에 어느 모델을 쓸지.
#
# 두 구간은 지연 요구가 완전히 다르다:
#   - 회의 중 자막: 사람이 기다리는 유일한 구간. 즉각성이 곧 UX.
#   - 회의록(정밀 재분석): 백그라운드라 지연 제약이 없음. 사용자가 보관·열람하는 최종본.
# 그래서 실시간은 빠른 모델(turbo), 최종본은 정확한 모델(large-v3)로 나눈다.
#
# 실측 근거 (2026-07-29, AI Hub 회의 음성 held-out 500건):
#   large-v3 + v4 어댑터 : CER 10.80% / 1.73초·건
#   large-v3-turbo       : CER 12.15% / 0.26초·건  (6.6배 빠름, 정확도 1.35%p 손해)
# 실시간 자막은 어차피 잠정 표시이고 몇 초 뒤 확정본으로, 회의 후엔 재분석본으로 대체되므로
# 이 구간의 1.35%p를 내주고 6.6배 응답성을 얻는 편이 낫다고 판단.
#
# ⛔ 2026-07-29: 실제 회의 음성으로 검증한 결과 False로 되돌림.
#
# AI Hub 평가셋(일반 회의 음성)에서는 1.35%p 차이였지만, 정작 우리 회의에서 중요한
# **팀 용어**에서 turbo가 확실히 뒤졌다. 같은 오디오(참가자 트랙)를 둘로 전사한 결과:
#     large-v3 : "임베딩 처리하고 있습니다 ... 웹소켓 재연결 로직"
#     turbo    : "인베딩 처리하고 있습니다 ... 랩소켓 재연결 로직"
# 전문용어 인식이 이 제품의 차별점이라, 여기서 지는 건 6.6배 속도로도 상쇄가 안 된다.
#
# 응답성 손해가 생각보다 작다는 점도 고려했다 — 회의 중 "실시간으로 흐르는" 느낌은
# 1초 주기 잠정 전사(partial, turbo)가 이미 담당하고, 확정본은 그걸 뒤에서 교정하는
# 역할이라 몇 초 늦어도 체감이 크지 않다.
#
# True로 켜면 실시간 확정도 turbo가 담당한다(속도 우선이 필요할 때).
REALTIME_FINAL_USES_FAST_MODEL = os.getenv("REALTIME_FINAL_USES_FAST_MODEL", "0").strip().lower() not in ("0", "false", "no")

# 신뢰도 게이팅 임계값 (이 기준 미달이면 모순 감지 엔진으로 안 보내고 보류)
#
# greedy(beam=1)로 전환하면서 재조정함. avg_logprob는 beam search일 때와 greedy일 때
# 계산 경로가 다른데(whisper_engine._compute_avg_logprob 참고), 실측해보니 둘 다
# "토큰당 평균 로그확률"이라 스케일 자체는 호환됐다. 다만 greedy는 매 스텝 최댓값을
# 고르는 구조라 값이 위로 쏠린다 — 실측 분포(세그먼트 200개, v4 어댑터):
#   beam=10: 중앙 -0.202 / p05 -0.812 / 최소 -1.396 → -1.0 미달 2.5%
#   beam=1 : 중앙 -0.152 / p05 -0.512 / 최소 -0.913 → -1.0 미달 0.0%(게이트 무력화)
# 그래서 기존 -1.0을 그대로 두면 게이트가 한 번도 안 걸려 조용히 죽는다.
# beam=10에서 -1.0이 하위 2.5%를 걸러내던 역할을 greedy 분포에서 하도록 -0.65로 내림.
#
# 주의: 이건 "같은 비율을 걸러내도록" 맞춘 근사치이지, 실제 오류율과의 상관을 보고
# 최적화한 값이 아니다. 정밀 보정은 세그먼트별 avg_logprob ↔ 실제 CER 상관 측정이 필요.
CONF_AVG_LOGPROB_THRESHOLD = -0.65  # 이보다 낮으면(음수로 클수록 나쁨) 신뢰도 낮음
CONF_NO_SPEECH_THRESHOLD = 0.6      # 이보다 높으면 침묵/노이즈를 잘못 들었을 가능성

# VAD 기반 청크 분할 설정 (시간이 아니라 '말이 끊기는 지점' 기준으로 자름)
REALTIME_SAMPLE_RATE = 16000
REALTIME_MIN_CHUNK_SEC = 2      # 너무 짧은 청크는 흘려보내지 않음
REALTIME_MAX_CHUNK_SEC = 28     # 침묵이 안 와도 이 길이가 되면 강제로 자름
REALTIME_SILENCE_MS = 500       # 이만큼 침묵이 지속되면 발화 구간 종료로 판단
REALTIME_FLUSH_CHECK_INTERVAL_SEC = 0.3  # VAD 기반 flush 판정 주기 (매 프레임 돌리면 CPU 낭비)
REALTIME_FLUSH_MIN_TAIL_SEC = 0.5        # 회의 종료 시 이보다 짧은 잔여 버퍼는 버림 (노이즈 수준)

# 강제 컷(REALTIME_MAX_CHUNK_SEC 도달) 시 단어 중간이 잘리는 걸 완화하기 위한 설정.
# 정상 침묵 판정(REALTIME_SILENCE_MS=500ms)까진 못 기다려도, 최근 구간 안에서
# 아주 짧은 틈이라도 있으면 그 지점에서 자르고 나머지는 다음 청크로 넘긴다.
# (둘 다 못 찾으면 기존처럼 버퍼 끝에서 그냥 강제로 자름 — 최후 수단)
REALTIME_FORCE_CUT_LOOKBACK_SEC = 3.0
REALTIME_FORCE_CUT_MIN_SILENCE_MS = 100

# Local Agreement 스트리밍 설정 — 발화자가 안 쉬고 계속 말해도
# 청크가 끝나기 전에 미리 텍스트를 흘려보내기 위한 파라미터
REALTIME_PARTIAL_INTERVAL_SEC = 1.0   # 이 주기로 버퍼 전체를 다시 훑어 잠정 텍스트 갱신
REALTIME_PARTIAL_MIN_SEC = 1.0        # 이보다 짧은 버퍼는 아직 잠정 전사 안 함

# ──────────────────────────────────────────
# 인식 힌트(initial_prompt) 설정
# ──────────────────────────────────────────
# 2026-07-15에 hotwords를 제거하고 파인튜닝으로 방향을 틀었으나("임의로 고른 단어 목록이라
# 근거가 약하다"는 이유), 2026-07-27 실측에서 파인튜닝의 실음성 개선폭이 CER 11.66%→11.18%
# (0.48%p)에 그쳐 숫자·고유명사 오인식을 잡지 못하는 것이 확인됨
# (실제 오인식: "8001번 포트"→"810000", "승주"→"승준", "WAV"→"WEV", "임베딩"→"인벨딩").
#
# 재도입하는 근거: 이제 "회의 참석자 명단"이라는 확실한 출처가 생겼음 — WebSocket이
# attendees/participant_name으로 이미 받고 있어서, 임의로 고른 목록이 아니라 그 회의에
# 실제로 참여 중인 사람 이름을 힌트로 줄 수 있다.
#
# ⛔ 2026-07-29: 실시간 회의에서 인식이 무너져 기본값을 끔으로 되돌림.
#
# 무슨 일이 있었나: 짧은 청크(2~3초)에서 모델이 오디오 대신 **프롬프트 문장 자체를
# 받아적었다.** 실제 회의록에 남은 결과:
#     '참석자&영어팀 회의. 참섭자&영어필.'
#     '참석자&용어&'
# Whisper의 initial_prompt는 "앞서 나온 문맥"으로 주입되는데, 실제 음성 정보가 적은
# 짧은 청크에서는 모델이 그 문맥의 패턴을 이어서 생성해버린다. 목록형 프롬프트
# ("용어: A, B, C, ...")는 특히 이어붙이기 쉬운 형태라 더 취약했다.
#
# 왜 사전에 못 잡았나: 검증을 파일 단위 긴 오디오(AI Hub 클립, 125초 회의 녹음)로만 했다.
# held-out CER이 안 나빠졌고 confident도 정상이라 통과시켰는데, **실시간 짧은 청크
# 경로에서는 한 번도 돌려보지 않았다.** 조건이 다른 데서 검증하고 통과시킨 실수.
#
# 버릴 아이디어는 아니다 — 같은 회의 오디오에서 "승주→승준", "WAV→외로", "STT→에스티티"
# 오인식을 실제로 고쳤다(제보 4건 중 3건 해결). 적용 방식이 틀렸을 뿐이다.
# 다시 켤 때 지켜야 할 것:
#   1) 프롬프트를 훨씬 짧게 — 참석자 이름만 쓰고 용어 목록은 빼는 방향부터 시도
#   2) 짧은 청크에는 적용하지 않기(예: 일정 길이 이상에서만)
#   3) 반드시 **실시간 경로**에서 검증 — 파일 단위 평가만으로는 이 문제를 못 잡는다
#
# INITIAL_PROMPT_ENABLED=1로 실험은 가능하되, 기본값은 끔.
INITIAL_PROMPT_ENABLED = os.getenv("INITIAL_PROMPT_ENABLED", "0").strip().lower() not in ("0", "false", "no")
TERMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terms.txt")

# LoRA 파인튜닝 어댑터 경로 — 설정 시 정밀(Precise) 모델에만 적용됨
# (어댑터가 large-v3 기준으로 학습됐고, fast 모델은 turbo라 구조가 다름).
#
# ⛔ 2026-07-29: 쓰지 않기로 결론. 파인튜닝은 다섯 번 시도해 모두 성과가 없었다.
#   v4 (large-v3, AI Hub 5K)         : CER 11.66% → 11.18% (0.48%p)
#   v5 (large-v3, 25K + MLP까지)      : CER 12.96% — 오히려 악화
#   ghost613/...turbo-korean         : CER 30.82% — 사용 불가
#   o0dimplz0o/...Zeroth-KO-v2       : CER 12.00% — turbo 순정(12.15%)과 노이즈 차
#   그리고 결정적으로, 팀 용어가 잔뜩 든 실제 회의 음성을 순정 large-v3와 v4 어댑터로
#   각각 전사해보니 **출력이 글자 하나까지 완전히 동일**했다. 어댑터가 실제 음성에서
#   아무것도 바꾸지 않는다는 뜻 — AI Hub에서 보이던 0.48%p조차 실사용에선 나타나지 않는다.
#
# 기본값 None 유지(=미적용). 재실험할 때만 환경변수로 켤 것.
LORA_ADAPTER_PATH = os.getenv("LORA_ADAPTER_PATH")

# ──────────────────────────────────────────
# pyannote 화자 분리 설정
# ──────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN")
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"
# 회의는 정의상 2명 이상이므로 하한을 2로 둔다.
# 1을 허용하면 pyannote가 "전원 동일인"이라는 결론을 낼 자유가 생기는데, 실측(2인 대화 125초)에서
# 발화 구간 18개를 전부 한 화자로 묶어버려 화자분리가 통째로 무력화됐다. 임베딩 자체는 두 목소리를
# 잘 갈라내고 있었다(같은 화자 0.62~0.75 vs 다른 화자 0.35~0.44)는 점에서, 원인은 임베딩 품질이
# 아니라 클러스터링에 준 이 하한값이었다.
# 트레이드오프: 1인 녹음(개발 중 혼자 하는 테스트 등)에서는 한 목소리가 둘로 쪼개질 수 있다.
# 제품 상황(회의)이 아니라 테스트 상황에서만 생기는 문제라 감수한다.
MIN_SPEAKERS = 2
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


def _load_prompt_terms() -> list[str]:
    """terms.txt를 읽어 용어 목록을 반환. '#' 시작 줄은 주석(선정 근거 기록용)."""
    if not os.path.isfile(TERMS_PATH):
        logger.warning(f"⚠️ 용어 목록 파일 없음: {TERMS_PATH} — 인식 힌트에 용어를 넣지 않음")
        return []
    with open(TERMS_PATH, encoding="utf-8") as f:
        return [s for s in (line.strip() for line in f) if s and not s.startswith("#")]


PROMPT_TERMS = _load_prompt_terms() if INITIAL_PROMPT_ENABLED else []


def build_initial_prompt(speaker_names=None) -> str | None:
    """
    회의 참석자 이름과 팀 용어를 Whisper 디코딩 힌트 문장으로 조립.

    speaker_names: 이 회의에 실제로 참여 중인 사람 이름들(공용 마이크 모드는 등록 참석자,
    각자 PC 모드는 본인 이름). 이름이 힌트에 들어가야 "승주"→"승준" 같은 오인식이 잡힌다.

    넣을 내용이 하나도 없으면(비활성화됐거나 이름·용어가 모두 비었으면) None을 반환해서
    호출부가 힌트 없이 그냥 전사하게 한다 — 알맹이 없는 문장만 주면 이득 없이 위험만 있음.
    """
    if not INITIAL_PROMPT_ENABLED:
        return None

    names = sorted({n.strip() for n in (speaker_names or []) if n and n.strip()})
    if not names and not PROMPT_TERMS:
        return None

    parts = ["비고 프로젝트 팀 회의."]
    if names:
        parts.append("참석자: " + ", ".join(names) + ".")
    if PROMPT_TERMS:
        parts.append("용어: " + ", ".join(PROMPT_TERMS) + ".")
    return " ".join(parts)