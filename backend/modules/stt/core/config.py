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
#
# STT_ENGINE=qwen 은 Whisper 계열이 아닌 Qwen3-ASR을 쓴다. 팀 용어 인식과 속도에서
# 실측 우위가 확인됐지만(qwen_engine.py 상단 참고) 숫자를 발음형으로 출력하는
# 미해결 결함이 있어 기본값으로 두지 않고 환경변수로만 켠다.
ARCH = platform.machine()
_env_engine = os.getenv("STT_ENGINE", "").strip().lower()
if _env_engine in ("faster_whisper", "transformers", "qwen"):
    STT_ENGINE = _env_engine
elif DEVICE == "cuda":
    # GPU 서버 기본값 = qwen (2026-07-30 실시간 회의 검증 후 전환).
    # CPU에서는 2B 모델이 실용 속도가 안 나오므로 아래 Whisper 경로를 그대로 둔다
    # — 맥 로컬 개발 환경이 여기 해당.
    STT_ENGINE = "qwen"
elif ARCH == "aarch64":
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

if STT_ENGINE == "qwen":
    WHISPER_MODEL_SIZE = os.getenv("QWEN_ASR_MODEL", "Qwen/Qwen3-ASR-1.7B-hf")
    # 잠정(partial) 전사는 1초마다 버퍼 전체(최대 28초)를 다시 훑는다. 여기에 확정용
    # 2B 모델을 쓰면 처리가 오디오 유입 속도를 못 따라가 전사 큐가 포화되고 프레임이
    # 버려진다(실측 확인 — 확정 지연 1.5~3.5초, 큐 포화 경고 폭주).
    # Whisper에서 확정=large-v3 / 잠정=turbo로 나눴던 것과 같은 이유다. 잠정 텍스트는
    # 어차피 확정 패스가 덮어쓰므로 정확도를 조금 양보해도 된다.
    WHISPER_MODEL_FAST = os.getenv("QWEN_ASR_MODEL_FAST", "Qwen/Qwen3-ASR-0.6B-hf")
    WHISPER_MODEL_PRECISE = WHISPER_MODEL_SIZE
elif STT_ENGINE == "transformers":
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

# ──────────────────────────────────────────
# 신뢰도 게이팅 임계값
# (이 기준 미달이면 confident=False로 표시 → 모순 감지 엔진이 경보를 보류)
# ──────────────────────────────────────────
# 2026-07-30 실측으로 재설정. 이전 값(-0.65)은 "beam 10에서 하위 2.5%를 걸러내던
# 역할을 greedy에서 재현"하도록 비율만 맞춘 근사치였고, 실제 오류율과의 상관을
# 보고 정한 값이 아니었다. 그 상관을 측정한 결과:
#
#   AI-Hub held-out 500건, avg_logprob 하위 구간의 평균 CER
#                   전체 평균   하위 2.5%   하위 5%   하위 10%   상위 5%
#     Whisper        8.82%      51.5%      35.9%     27.4%     1.7%
#     Qwen3-ASR     11.31%      59.5%      38.8%     32.6%     4.6%
#
# → avg_logprob는 품질 예측 신호로 확실히 유효하다(하위 5%가 평균의 4배 이상 틀림).
#   문제는 임계값이었다: -0.65는 Whisper 499건 중 2건(0.4%)만 걸러내서 게이트가
#   사실상 죽어 있었다. Qwen 분포에서는 0%로 완전히 무력.
#
# 하위 5% 지점을 기준으로 잡는다. 이 구간은 CER 36~39% — 글자 3분의 1 이상이 틀려
# 사실상 못 쓰는 텍스트다. 10%까지 넓히면 CER 27~33%로 "읽을 수는 있는" 구간까지
# 잡아 과차단이 되고, 2.5%로 좁히면 CER 51~59%짜리만 잡고 그 바로 위를 놓친다.
#
# ⚠️ 엔진마다 분포가 달라 값을 공유할 수 없다 — Qwen은 중앙값이 -0.03, Whisper는
#    -0.10으로 스케일이 3배 차이난다. 모델이나 beam 크기를 바꾸면 반드시 재측정할 것.
#    (측정 방법: evaluate_wer.py 리포트의 details[].avg_logprob와 cer를 상관 분석)
if STT_ENGINE == "qwen":
    CONF_AVG_LOGPROB_THRESHOLD = -0.11   # Qwen 분포 p05 = -0.1115
else:
    CONF_AVG_LOGPROB_THRESHOLD = -0.30   # Whisper 분포 p05 = -0.2981

# ⚠️ Qwen 엔진은 no_speech_prob를 내지 않아 항상 0.0이다(qwen_engine.py 참고).
#    즉 qwen에서는 이 검사가 무력하고 신뢰도가 avg_logprob 하나에만 걸린다.
#    VAD(trim_silence)가 순수 침묵을 이미 걸러주므로 실사용상 문제는 없지만,
#    "신뢰도 신호가 두 개"라고 가정하는 코드를 새로 쓰면 안 된다.
CONF_NO_SPEECH_THRESHOLD = 0.6      # 이보다 높으면 침묵/노이즈를 잘못 들었을 가능성


def is_confident(avg_logprob: float | None, no_speech_prob: float | None) -> bool:
    """
    세그먼트를 신뢰할 수 있는지 판정 — 이 판단의 **유일한** 구현.

    임계값과 판정 로직을 한곳에 두는 이유: 예전엔 실시간(realtime_service), 정밀
    재분석(refine_service), 배치 업로드(pipeline) 세 경로가 각자 판정했고 배치
    경로는 아예 빠뜨려서 팀 공통 스키마(confident 필드)를 위반하고 있었다.
    임계값을 조정할 때 한 곳만 고치면 나머지가 조용히 낡는 구조였다.

    값이 없으면(엔진이 해당 신호를 주지 않으면) 통과시킨다 — 신호 부재를
    '신뢰 못 함'으로 처리하면 전부 저신뢰로 표시돼 플래그가 무의미해진다.
    (Qwen 엔진은 no_speech_prob를 내지 않아 항상 0.0이다.)
    """
    if avg_logprob is not None and avg_logprob < CONF_AVG_LOGPROB_THRESHOLD:
        return False
    if no_speech_prob is not None and no_speech_prob > CONF_NO_SPEECH_THRESHOLD:
        return False
    return True

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

# 잠정 자막에 화자를 붙일 때 쓸 오디오 길이(버퍼 끝에서부터).
#
# 화자 식별은 침묵과 무관하다 — 임베딩 하나 뽑아 등록 프로필과 코사인 비교하는 게
# 전부라 1초 이상 오디오만 있으면 언제든 판정된다. 그런데 확정 청크(VAD가 침묵으로
# 끊어줄 때까지 최대 28초)에서만 화자를 붙이고 있어서, 회의 중 화면에는 대부분의
# 시간 동안 화자 없는 텍스트만 흘렀다.
#
# 버퍼 '전체'가 아니라 '끝부분'만 쓰는 게 핵심이다. 버퍼 전체에는 여러 사람이 섞여
# 있을 수 있지만, 끝 2초는 지금 말하고 있는 한 사람일 가능성이 매우 높다.
# 짧을수록 화자 전환을 빨리 따라가지만 1초 미만은 임베딩이 불안정하다
# (speaker_id_service._MIN_EMBED_SEC).
REALTIME_PARTIAL_SPEAKER_TAIL_SEC = 2.0

# 확정 청크 안에서 화자가 바뀌면 그 지점에서 나눠 각각 전사할지.
#
# 청크는 VAD가 침묵을 찾을 때까지 최대 28초까지 늘어나는데, 두 사람이 쉼 없이 주고받으면
# 한 청크에 여러 화자가 들어간다. 예전에는 청크 전체에 화자 라벨 하나만 붙어서
# "질문과 답변이 한 사람 발언으로 묶이는" 결과가 나왔다.
#
# 화자 전환이 없는 청크(대부분)에서는 분할이 일어나지 않아 기존과 동일하게 동작한다.
# 끄면 청크당 화자 하나를 배정하던 이전 동작으로 돌아간다.
REALTIME_SPEAKER_SPLIT_ENABLED = os.getenv("REALTIME_SPEAKER_SPLIT_ENABLED", "1").strip().lower() not in ("0", "false", "no")

# 화자 전환을 찾을 때 발화 구간을 나누는 침묵 길이.
#
# ⚠️ REALTIME_SILENCE_MS(청크를 끊는 기준)보다 반드시 짧아야 한다. 같으면 기능이
# 사실상 죽는다 — 간격이 그보다 길면 청크가 거기서 끊겨 화자당 청크 하나가 되니
# 분할할 게 없고, 짧으면 VAD가 발화를 하나로 봐서 분할할 근거가 없다. 두 조건 사이
# 좁은 창에서만 발동하는 셈이다(실시간 검증에서 0회 나온 원인).
#
# 짧게 잡을수록 빠른 주고받기까지 잡아내지만, 한 사람의 말 중간 호흡까지 구간으로
# 쪼개 판정 횟수가 늘어난다. 쪼개져도 같은 화자로 판정되면 다시 하나로 병합되므로
# 결과는 안전하고 비용만 조금 는다.
REALTIME_SPEAKER_SPLIT_SILENCE_MS = int(os.getenv("REALTIME_SPEAKER_SPLIT_SILENCE_MS", "200"))

# 침묵으로 못 나눌 때 **목소리 변화로** 한 번 더 나눌지.
#
# 침묵 기준만으로는 "쉼 없이 주고받는" 대화를 못 나눈다 — 나눌 침묵이 자체가 없다.
# 실측(팀 제보): "네, 제가 이번 주 안으로 반영해 볼게요. 감사합니다. 오늘은 여기까지
# 할게요."가 한 사람으로 묶였다(앞은 김나연, 뒤는 문지수). 회의 중 자막에 틀린 이름이
# 뜨는 것이라 눈에 띈다.
#
# 비용은 창 수에 비례한다 = 곧 확정 자막의 지연이다. 그래서 재분석(0.5초 이동)보다
# 성기게 훑고, 짧은 청크는 아예 건너뛴다(짧으면 화자가 바뀔 여지도 적다).
# 전사 결과를 문장 단위로 쪼개 내보낼지. 모순 감지 모델이 "발화 하나"를 받도록
# 만들어졌는데, Qwen은 창 하나당 텍스트 한 덩어리를 주므로 우리가 쪼개야 한다
# (realtime_service._split_by_sentence 참고 — 실측 근거가 거기 있다).
REALTIME_SENTENCE_SPLIT_ENABLED = os.getenv("REALTIME_SENTENCE_SPLIT_ENABLED", "1").strip().lower() not in ("0", "false", "no")
# 이보다 짧은 조각은 독립 세그먼트로 두지 않고 앞 조각에 붙인다.
# "네." "갑자기요." 같은 맞장구가 조각으로 쏟아지면 판단이 오히려 더 헷갈린다.
# (버리지는 않는다 — 붙이지 않고 통째로 안 쪼개면, 정작 고치려던 긴 덩어리가 그대로 남는다)
REALTIME_SENTENCE_MIN_CHARS = int(os.getenv("REALTIME_SENTENCE_MIN_CHARS", "6"))

REALTIME_SPEAKER_SCAN_ENABLED = os.getenv("REALTIME_SPEAKER_SCAN_ENABLED", "1").strip().lower() not in ("0", "false", "no")
REALTIME_SPEAKER_SCAN_MIN_SEC = float(os.getenv("REALTIME_SPEAKER_SCAN_MIN_SEC", "4.0"))
REALTIME_SPEAKER_SCAN_HOP_SEC = float(os.getenv("REALTIME_SPEAKER_SCAN_HOP_SEC", "0.75"))

# ──────────────────────────────────────────
# 회의 중 오디오 품질 경고 (services/audio_quality.py)
# ──────────────────────────────────────────
# 2026-08-05: 대본까지 준비한 5인 모의 회의가 CER 31.8%로 나왔다(평소 6% 수준).
# 원인은 배경 소음이었고 — SNR이 잘 나온 회의의 18.9dB에서 8.8dB로 떨어져 있었다 —
# **회의가 끝난 뒤에야 알았다.** 마이크를 옮기거나 창문을 닫는 건 회의 초반에
# 알려주면 할 수 있는 일이다. 그래서 사후 보고가 아니라 초반 경고를 목표로 한다.
#
# ⚠️ 문턱은 좋은 회의 1건·나쁜 회의 1건, **표본 두 개로 정한 잠정값**이다.
#    오경보가 잦으면 사람들이 경고를 무시하게 되므로 확실히 나쁠 때만 뜨도록
#    보수적으로 잡았다(실측 8.8dB는 잡고 18.9dB는 안 잡는 선에서 아래쪽에 가깝게).
#    표본이 쌓이면 조정할 것.
AUDIO_WARN_MIN_SPEECH_SEC = float(os.getenv("AUDIO_WARN_MIN_SPEECH_SEC", "15"))
AUDIO_WARN_SNR_DB = float(os.getenv("AUDIO_WARN_SNR_DB", "12"))
AUDIO_WARN_SPEECH_RMS = float(os.getenv("AUDIO_WARN_SPEECH_RMS", "0.02"))
AUDIO_WARN_CLIP_RATIO = float(os.getenv("AUDIO_WARN_CLIP_RATIO", "0.001"))
# 소리가 아예 안 들어오는 건 판단에 오래 걸릴 이유가 없다 — 마이크 미선택/음소거는
# 빨리 알려줄수록 좋다.
AUDIO_WARN_NO_SPEECH_SEC = float(os.getenv("AUDIO_WARN_NO_SPEECH_SEC", "30"))

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
#
# ⚠️ 위 내용은 Whisper 계열에 해당한다. Qwen3-ASR은 컨텍스트 바이어싱을 학습에
# 포함한 모델이라 훨씬 견고하고(용어 재현율 80.7%→92.8%, 속도 비용 0) 실사용에서
# 문제 없이 쓰고 있지만, **면역은 아니다** — 2026-07-31 실제 회의에서 짧고 불분명한
# 구간 하나가 용어 목록을 그대로 받아적은 사례가 관측됐다. qwen_engine의
# _is_context_echo가 그런 출력을 걸러낸다.
INITIAL_PROMPT_ENABLED = os.getenv("INITIAL_PROMPT_ENABLED", "0").strip().lower() not in ("0", "false", "no")
TERMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terms.txt")
# Qwen 컨텍스트용 목록은 따로 둔다 — Whisper 프롬프트의 제약(목록형 취약성,
# 224토큰 한계)이 Qwen에는 없어서 넓게 담는 게 이득이기 때문. terms_context.txt 헤더 참고.
QWEN_TERMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "terms_context.txt")

# ──────────────────────────────────────────
# Qwen3-ASR 컨텍스트 바이어싱
# ──────────────────────────────────────────
# Whisper의 initial_prompt와 통로는 같아 보이지만 성질이 다르다. Whisper는 프롬프트를
# "앞서 나온 문맥"으로 해석해 짧은 청크에서 그대로 받아적는 사고를 냈지만, Qwen은
# 컨텍스트 주입을 학습으로 배운 기능이라 용어 목록을 그대로 넣어도 안전하다.
# 실측(우리 팀 녹음 40건): 용어 재현율 85.5% → 92.8%, CER 7.46% → 5.62%, 속도 변화 없음.
#
# 단, 어휘에만 작동한다. "숫자는 아라비아 숫자로 표기" 같은 출력 형식 지시문은
# 효과가 없음이 실측으로 확인됐다(CER 9.12% → 9.25%, 노이즈 범위).
QWEN_CONTEXT_ENABLED = os.getenv("QWEN_CONTEXT_ENABLED", "1").strip().lower() not in ("0", "false", "no")

# Qwen은 ITN을 적용하지 않아 숫자를 발음형으로 출력한다("8002번" → "팔천이번").
# 회의록에서 포트 번호·버전·날짜는 모순 감지가 직접 비교하는 값이라 숫자 형태여야 하므로
# 후처리로 되돌린다(utils/korean_itn.py). 오변환이 의심되면 0으로 꺼서 원문을 확인할 것.
QWEN_ITN_ENABLED = os.getenv("QWEN_ITN_ENABLED", "1").strip().lower() not in ("0", "false", "no")

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
# ──────────────────────────────────────────
# 정밀 재분석 완료 웹훅
# ──────────────────────────────────────────
# 재분석은 회의 종료 후 백그라운드로 돌고, 그때 클라이언트 WebSocket은 이미 닫혀 있어
# 완료를 알릴 통로가 없었다. 소비자(백엔드 요약/모순감지)가 refined 플래그를 폴링하는
# 대신 완료 시점에 한 번 POST로 찔러준다. services/refine_webhook.py 참고.
#
# 미설정(None)이면 웹훅을 보내지 않는다 — 기존 동작과 동일.
REFINE_WEBHOOK_URL = os.getenv("REFINE_WEBHOOK_URL") or None
REFINE_WEBHOOK_TIMEOUT_SEC = float(os.getenv("REFINE_WEBHOOK_TIMEOUT_SEC", "10"))
# 수신 측이 요구하는 인증 헤더. 시크릿은 자격증명이므로 절대 코드/설정 파일에 넣지 말고
# 환경변수로만 주입할 것 (.env는 gitignore 대상).
REFINE_WEBHOOK_SECRET = os.getenv("REFINE_WEBHOOK_SECRET") or None
REFINE_WEBHOOK_SECRET_HEADER = os.getenv("REFINE_WEBHOOK_SECRET_HEADER", "X-Webhook-Secret")
# 소비자 서버가 재시작 중일 수 있어 재시도한다. 통지를 놓치면 소비자 쪽 후처리가
# 아예 시작되지 않으므로 한 번 실패로 포기하지 않는다(지연은 delay × 시도횟수로 증가).
REFINE_WEBHOOK_RETRIES = int(os.getenv("REFINE_WEBHOOK_RETRIES", "3"))
REFINE_WEBHOOK_RETRY_DELAY_SEC = float(os.getenv("REFINE_WEBHOOK_RETRY_DELAY_SEC", "2"))

# ──────────────────────────────────────────
# 회의록 LLM 문맥 교정 (services/transcript_correction.py)
# ──────────────────────────────────────────
# 용어 목록(terms_context.txt)은 "틀린 단어를 발견할 때마다 사람이 추가"하는 방식이라
# 목록에 없는 단어는 계속 틀린다. 이해가 아니라 암기다.
# LLM은 문맥으로 유추한다 — "이전 결정 반복하고"가 어색하다는 걸 알아서 "번복"으로
# 고친다. 목록에 그 단어가 있어서가 아니다.
#
# 재분석(백그라운드)에서만 돈다. 실시간 자막에 물리면 응답성이 무너진다.
# 미설정이면 꺼져 있다 — LLM 서버가 없는 환경에서도 재분석은 그대로 동작해야 한다.
REFINE_LLM_ENABLED = os.getenv("REFINE_LLM_ENABLED", "0").strip().lower() not in ("0", "false", "no")
# 교정을 어디에 맡길지. "ollama"는 팀이 띄운 서버(주소 필요, 그쪽에 부하),
# "local"은 이 서버에 받아둔 모델을 직접 돌린다(남에게 안 기대지만 GPU 메모리를 씀).
REFINE_LLM_BACKEND = os.getenv("REFINE_LLM_BACKEND", "ollama").strip().lower()
REFINE_LLM_URL = os.getenv("REFINE_LLM_URL", "http://127.0.0.1:11434")
# local 백엔드가 쓸 모델. 4bit 기본 — STT 모델들과 GPU를 나눠 써야 한다.
REFINE_LLM_LOCAL_MODEL = os.getenv(
    "REFINE_LLM_LOCAL_MODEL", "unsloth/Qwen2.5-7B-Instruct-unsloth-bnb-4bit",
)
REFINE_LLM_MODEL = os.getenv("REFINE_LLM_MODEL", "qwen2.5:14b")
REFINE_LLM_TIMEOUT = float(os.getenv("REFINE_LLM_TIMEOUT", "120"))
# 한 번에 고칠 줄 수. 너무 크면 모델이 뒤쪽 줄을 대충 보고, 너무 작으면 호출이 잦아진다.
REFINE_LLM_BATCH = int(os.getenv("REFINE_LLM_BATCH", "20"))
# 고칠 구간 앞뒤로 같이 보여줄 줄 수. **문맥으로 판단하게 하는 것이 이 기능의 전부**라
# 0으로 두면 쓸 이유가 없다.
REFINE_LLM_CONTEXT_LINES = int(os.getenv("REFINE_LLM_CONTEXT_LINES", "5"))
# 글자 변경 비율이 이보다 크면 교정을 거부한다 — "문장을 통째로 다시 쓰는" 사고를
# 막는 마지막 방어선이다. 전사가 조금 틀린 것보다 내용이 바뀌는 쪽이 훨씬 나쁘다
# (모순 감지가 없던 모순을 만든다).
#
# 실측된 네 사례로 정했다(편집거리 기준):
#   단어 하나 교정(반복→번복)           4%   ← 통과해야 함
#   두 곳 교정(동마크→북마크 등)        18%   ← 통과해야 함
#   앞부분 교정(그런 제목→재분석)       29%   ← 통과해야 함
#   문장 재작성(말투·어순 전면 수정)    81%   ← 차단해야 함
# 29%와 81% 사이가 크게 벌어져 있어 0.35로 잡았다.
#
# ⚠️ 처음엔 0.25였는데 정당한 교정이 막혔다. 그 전에는 변경률 계산 자체가 틀려서
#    (공통 접두/접미만 보는 방식) 18%짜리가 96%로 계산돼 거부됐다 — 문턱보다
#    측정이 먼저 맞아야 한다.
REFINE_LLM_MAX_EDIT_RATIO = float(os.getenv("REFINE_LLM_MAX_EDIT_RATIO", "0.35"))

# ──────────────────────────────────────────
# 겹쳐 말한 구간 처리 (services/overlap_detect.py, speech_separation.py)
# ──────────────────────────────────────────
# 겹친 목소리에서 한 명을 고르는 것은 **정답이 "여러 명"인 질문에 한 명으로 답하는 것**
# 이라 무조건 틀린다. 실측: 대본상 전원이 동시에 말한 "네 좋습니다"에 이승주 이름이 붙었다.
#
# 겹침으로 볼 최소 길이. 이보다 짧으면 화자분리 경계의 오차일 뿐 실제로 겹쳐 말한 게 아니다.
OVERLAP_MIN_SEC = float(os.getenv("OVERLAP_MIN_SEC", "0.3"))
# 세그먼트의 이 비율 이상이 겹침이면 화자를 정하지 않는다(overlapped=True, speaker=null).
# 부분 겹침(긴 발언 중 누가 "네" 하고 끼어드는 것)은 화자가 여전히 명확하므로 건드리지 않는다.
OVERLAP_SEGMENT_RATIO = float(os.getenv("OVERLAP_SEGMENT_RATIO", "0.6"))
# 겹침 감지에 쓰는 모델. 화자분리(diarization-3.1)가 내부적으로 의존하는 것과 같은
# 모델이라 이미 받아져 있다. 화자분리 결과에서 겹침을 역산하던 방식은 오탐이 많아
# 폐기했다 — 그 방식이 찾은 11개 구간을 이 모델로 재보니 하나도 겹침이 아니었다.
OVERLAP_MODEL = os.getenv("OVERLAP_MODEL", "pyannote/segmentation-3.0")
# multilabel 출력에서 "이 사람이 지금 말한다"로 볼 확률 문턱.
# 낮추면 겹침을 더 잡지만 오탐(멀쩡한 발언에 '여러 명' 표시)도 늘어난다.
OVERLAP_ACTIVE_THRESHOLD = float(os.getenv("OVERLAP_ACTIVE_THRESHOLD", "0.5"))

# 겹친 세그먼트의 화자 이름을 지울지.
#
# **기본은 지우지 않는다** — 실측 결과 지울 근거가 안 나왔기 때문이다.
# 처음 의도는 "전원이 동시에 말한 줄에서 한 명을 고르지 않게" 하는 것이었고,
# 맞장구와 전원 응답은 동시 화자 수로 갈릴 거라 봤다. 그런데 pyannote는 전원이
# 답한 구간도 2명으로만 잡는다(3명 이상 동시 발화 0건). 즉 두 경우가 구분되지 않는다.
# 2명 기준으로 지우면 오배정 1개를 고치는 대신 맞는 이름 6개를 잃는다 — 손해다.
#
# 그래서 이름은 두고 overlapped 표시만 단다. 잃는 것이 없고, 모순 감지가 이 표시를
# 보고 해당 발언을 걸러내면 **틀린 이름이 실제로 해를 끼치는 지점은 막힌다.**
# 겹침을 제대로 가르려면 전용 겹침 감지 모델이 필요하다(미검증).
OVERLAP_CLEAR_SPEAKER = os.getenv("OVERLAP_CLEAR_SPEAKER", "0").strip().lower() not in ("0", "false", "no")

# 겹친 구간을 화자별 음원으로 분리해 각각 전사한다(포기하는 대신 둘 다 살린다).
# ⚠️ 기본 꺼짐 — 무겁고, 모델을 서버에서 쓸 수 있는지 확인이 필요하다.
#    finetune/stt/probe_separation.py로 확인한 뒤 켤 것.
#    두 명 겹침은 쓸 만하지만 세 명 이상이면 급격히 나빠진다.
SEPARATION_ENABLED = os.getenv("SEPARATION_ENABLED", "0").strip().lower() not in ("0", "false", "no")
SEPARATION_MODEL = os.getenv("SEPARATION_MODEL", "pyannote/speech-separation-ami-1.0")
# 분리 모델은 화자 수만큼 채널을 항상 만들므로, 그 사람이 말하지 않은 구간에도 잔향이 남는다.
# 이 세기(RMS) 미만인 채널은 그 구간에서 말하지 않은 것으로 보고 전사하지 않는다 —
# 안 그러면 무음을 전사해 헛것이 나온다.
SEPARATION_MIN_ENERGY = float(os.getenv("SEPARATION_MIN_ENERGY", "0.01"))

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

# 이 유사도 미만이면 이름을 붙이지 않고 화자 미상(None)으로 둔다.
#
# ⚠️ **열린 집합 전용이다** (참석자를 미리 등록하지 않고 시작한 회의).
#    등록 안 된 사람이 말할 수 있으므로 "충분히 닮았나"를 절대 점수로 물어야 한다.
#
# 참석자를 아는 회의(attendees 지정)에는 쓰지 않는다 — 실측에서 이 문턱이 정답을
# 걷어내고 있었다. 5인 회의에서 이준오 0.360 / 이승주 0.302 / 김나연 0.286으로
# 평균 유사도가 전부 하한 미만인데 1등은 87~94% 맞혔다. 절대 점수는 프로필 품질에
# 따라 0.29~0.53으로 흩어져서 모두에게 같은 문턱을 씌우는 것 자체가 성립하지 않는다.
# 참석자를 알면 "충분히 닮았나"가 아니라 "누가 제일 닮았나"를 물어야 하고,
# 그쪽은 아래 SPEAKER_MIN_MARGIN이 담당한다.
#
# ⚠️ 이 값 때문에 세그먼트의 speaker가 null일 수 있다. 프론트/소비자는 이름 없이
#    텍스트만 표시하도록 처리해야 한다(잠정 자막은 이미 null을 허용한다).
SPEAKER_MIN_ASSIGN_SIMILARITY = float(os.getenv("SPEAKER_MIN_ASSIGN_SIMILARITY", "0.4"))

# ── 참석자를 아는 회의(닫힌 집합)의 화자 판정 ────────────────────────────────
# 절대 점수 대신 **순위**로 판정하고, 1등과 2등의 차이(margin)로만 걸러낸다.
#
# margin이 하는 일: 순위 판정은 무조건 누군가를 지목하므로, 침묵·잡음·겹쳐 말한
# 구간에도 이름이 붙는다. 그걸 막는 유일한 방어선이다.
# 실측(창 90개): 오답 창의 margin 0.028~0.078, 정답 창 평균 0.086~0.244.
# 문턱 0.05에서 91%를 살리고 정확도 98%.
SPEAKER_MIN_MARGIN = float(os.getenv("SPEAKER_MIN_MARGIN", "0.05"))

# 순위 1등이라도 이 유사도조차 안 되면 미상으로 둔다 — **명단 밖 목소리 차단용**.
#
# 왜 margin만으로는 부족한가: margin은 "명단 안에서 1·2등이 갈리는가"만 본다.
# 참석자가 아닌 사람이 말해도 특정 참석자 쪽으로 치우쳐 있으면 margin은 크게 나온다.
# 실측(5인 회의를 3명 명단으로): 명단 밖인 이준오의 56%, 이승주의 31%가 margin을
# 통과해 가동현·문지수 이름을 받았다. 회의가 끝난 뒤 잡음에 이름이 붙기도 했다.
#
# 절대 문턱(SPEAKER_MIN_ASSIGN_SIMILARITY=0.4)과 역할이 다르다. 그쪽은 "이 사람이
# 맞나"를 묻다가 정답까지 걷어냈다. 이건 "사람이긴 한가" 수준의 바닥이라 훨씬 낮다.
#
# 실측 분포(1.5초 창, 5인 회의): 명단 안 하위 5% 0.402 / 명단 밖 상위 5% 0.336.
#   0.35 → 명단 밖 100% 차단, 명단 안 95% 유지   ← 채택
#   0.30 → 명단 밖  90% 차단, 명단 안 98% 유지
#
# 0.30을 한 번 시도했다가 0.35로 되돌렸다. 0.35가 가동현의 답변 한 줄을 미상으로
# 떨어뜨려서 "바닥값이 정답을 자른다"고 봤는데, 실제로 내려보니 가동현이 돌아온 게
# 아니라 **그 자리에 문지수라는 틀린 이름이 들어왔다.** 그 구간은 순위 자체가
# 문지수를 1등으로 뽑고 있었고, 바닥값은 그 틀린 1등을 막고 있던 것이었다.
#
# ⇒ 미상은 "바닥값이 정답을 잘랐다"는 증거가 아니다. 1등이 애초에 틀렸을 수도 있다.
#    바닥값을 조정하기 전에 그 구간에서 누가 1등인지 먼저 확인할 것.
#    (틀린 이름보다 미상이 낫다 — 회의록에서 고칠 수 있고, 모순 감지가 엉뚱한
#     사람의 발언으로 판단하는 것도 막는다.)
#
# ⚠️ 이 값은 등록 프로필 품질에 직접 묶인다. 프로필이 부실한 사람이 하나라도 있으면
#    그 사람에 맞춰 바닥을 낮게 깔아야 하고, 그만큼 명단 밖이 새어든다.
#    실제로 그랬다 — 재등록 전에는 김나연 0.286 / 이준오 0.360이라 0.25까지밖에
#    못 올렸고(명단 밖 차단 52%), 셋을 재등록해 전원 0.46 이상이 되고서야 0.35가 됐다.
#    ⇒ 화자 판정이 나쁠 때는 알고리즘보다 **프로필부터 의심할 것.**
#       probe_window_speaker_id.py로 각자 유사도를 보고, 낮은 사람을 재등록한 뒤
#       probe_out_of_roster.py로 이 값을 다시 정한다.
#
# ⚠️ 위 수치는 회의 한 건에서 나왔고, 그중 세 명의 프로필이 바로 그 회의 오디오에서
#    만들어졌다(평가와 등록이 같은 오디오 = 순환). 새 녹음으로 반드시 재검증할 것.
SPEAKER_ABSOLUTE_FLOOR = float(os.getenv("SPEAKER_ABSOLUTE_FLOOR", "0.35"))

# 재분석에서 오디오를 훑는 창 크기와 간격.
# 1.5초는 임베딩이 안정되는 최소 길이(_MIN_EMBED_SEC=1.0)에 여유를 둔 값이고,
# 0.5초 간격이면 화자 경계를 그 정도 해상도로 잡는다 — 턴 배정에는 충분하다.
SPEAKER_WINDOW_SEC = float(os.getenv("SPEAKER_WINDOW_SEC", "1.5"))
SPEAKER_WINDOW_HOP_SEC = float(os.getenv("SPEAKER_WINDOW_HOP_SEC", "0.5"))

# 이웃 창 다수결로 순간적인 흔들림을 되돌린다 (실측 94% → 97%).
# 짝수로 두면 동점이 생기므로 홀수를 쓴다. 1이면 평활화 없음.
SPEAKER_SMOOTH_WIDTH = int(os.getenv("SPEAKER_SMOOTH_WIDTH", "3"))

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


def _load_prompt_terms(path: str = None) -> list[str]:
    """용어 목록 파일을 읽어 목록을 반환. '#' 시작 줄은 주석(선정 근거 기록용)."""
    path = path or TERMS_PATH
    if not os.path.isfile(path):
        logger.warning(f"⚠️ 용어 목록 파일 없음: {path} — 인식 힌트에 용어를 넣지 않음")
        return []
    with open(path, encoding="utf-8") as f:
        return [s for s in (line.strip() for line in f) if s and not s.startswith("#")]


PROMPT_TERMS = _load_prompt_terms() if INITIAL_PROMPT_ENABLED else []

# Qwen 컨텍스트는 용어 목록을 그대로 쓴다 — INITIAL_PROMPT_ENABLED와 별개로 켜진다.
QWEN_CONTEXT_TERMS = _load_prompt_terms(QWEN_TERMS_PATH) if (STT_ENGINE == "qwen" and QWEN_CONTEXT_ENABLED) else []


def build_qwen_context(speaker_names=None, extra_terms=None) -> str | None:
    """
    Qwen3-ASR 시스템 메시지에 넣을 컨텍스트 조립.

    build_initial_prompt()와 목적은 같지만 형태가 다르다. Whisper 쪽은 프롬프트가
    "앞 문맥"으로 해석돼 이어쓰기 사고가 나므로 문장형을 피할 수 없었지만, Qwen은
    컨텍스트를 별도 채널로 받으므로 목록을 그대로 나열하는 게 가장 잘 먹힌다.

    extra_terms: 이 회의에만 해당하는 용어(지난 회의록에서 수집한 것 등).
                 정적 목록 뒤에 붙는다. ⚠️ 목록 길이가 곧 지연이므로
                 (실측 204개 0.85초 / 3000개 2.15초) 호출부가 개수를 통제해야 한다.
    """
    if not (STT_ENGINE == "qwen" and QWEN_CONTEXT_ENABLED):
        return None

    names = sorted({n.strip() for n in (speaker_names or []) if n and n.strip()})
    terms = list(QWEN_CONTEXT_TERMS) + [t for t in (extra_terms or []) if t not in QWEN_CONTEXT_TERMS]
    if not names and not terms:
        return None

    parts = []
    if names:
        parts.append("참석자: " + ", ".join(names))
    if terms:
        parts.append("용어: " + ", ".join(terms))
    return " / ".join(parts)


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


# 지난 회의록에서 가져올 용어 수 상한. 목록 길이가 곧 지연이라 예산을 정해둔다
# (정적 204개 + 동적 50개 ≈ 250개, 실측상 1초 이내 유지되는 범위).
SESSION_TERMS_LIMIT = int(os.getenv("SESSION_TERMS_LIMIT", "50"))


def build_context_hint(speaker_names=None, session_id: str | None = None) -> str | None:
    """
    엔진에 맞는 용어/이름 힌트를 만든다. 호출부(realtime, refine)는 어느 엔진이
    돌고 있는지 몰라도 된다 — Whisper 계열은 프롬프트가 위험해서 기본 비활성이고
    Qwen은 컨텍스트가 안전해서 기본 활성인데, 그 판단을 여기 한 곳에 모아둔다.

    session_id를 주면 같은 회의 시리즈의 지난 회의록에서 용어를 추가로 수집한다
    (services/meeting_terms.py). 그 팀이 실제로 쓰는 말이 정적 목록보다 정확하다.
    """
    if STT_ENGINE != "qwen":
        return build_initial_prompt(speaker_names)

    extra = []
    if session_id and QWEN_CONTEXT_ENABLED:
        # 지연 임포트 — config는 services보다 먼저 로드되므로 상단 임포트는 순환이 된다
        from ..services.meeting_terms import collect_session_terms
        try:
            extra = collect_session_terms(
                session_id, set(QWEN_CONTEXT_TERMS), limit=SESSION_TERMS_LIMIT
            )
        except Exception:
            # 용어 수집 실패가 회의를 막으면 안 된다 — 정적 목록만으로 진행
            logger.exception(f"⚠️ [{session_id}] 지난 회의 용어 수집 실패 — 정적 목록만 사용")
    return build_qwen_context(speaker_names, extra_terms=extra)