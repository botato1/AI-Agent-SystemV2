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

# 닫힌 집합에서 이 유사도 미만이면 이름을 붙이지 않고 화자 미상(None)으로 둔다.
#
# 왜 필요한가: 닫힌 집합은 매칭이 아무리 나빠도 "가장 가까운 사람"에게 무조건 배정한다.
# 하한이 없으면 유사도 0.32짜리 판정에도 확신에 차서 이름이 붙는다.
# 실측(5인 회의 구간별): 정상 매칭은 0.72인데 오배정 구간은 0.32~0.37이고
# 1·2등 격차가 0.01~0.05로 사실상 구분이 안 되는 상태였다.
# **틀린 이름보다 "미상"이 낫다** — 회의록에서 사람이 고칠 수 있고, 모순 감지가
# 엉뚱한 사람의 발언으로 판단하는 것도 막는다.
#
# ⚠️ 이 값을 켜면 세그먼트의 speaker가 null일 수 있다. 프론트/소비자는 이름 없이
#    텍스트만 표시하도록 처리해야 한다(잠정 자막은 이미 null을 허용한다).
# 표본이 적어 잠정값이다 — 로그의 "화자 미상" 빈도를 보고 조정할 것.
SPEAKER_MIN_ASSIGN_SIMILARITY = float(os.getenv("SPEAKER_MIN_ASSIGN_SIMILARITY", "0.4"))

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