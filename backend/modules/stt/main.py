import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pyannote.audio import Pipeline

from .core.config import (
    logger, UPLOAD_DIR, MEETINGS_DIR, DEVICE, COMPUTE_TYPE, STT_ENGINE, WHISPER_MODEL_SIZE,
    WHISPER_MODEL_FAST, WHISPER_MODEL_PRECISE, DIARIZATION_MODEL, HF_TOKEN, LORA_ADAPTER_PATH
)
from .routers import stt, realtime, enroll, meetings, profiles
from .services.speaker_id_service import load_speaker_embedding_inference
from .services.profile_store import GlobalProfileStore


def _load_whisper_model(model_id: str, adapter_path: str | None = None):
    """
    STT_ENGINE에 따라 엔진을 분기 로딩.
    - faster_whisper(ctranslate2): x86_64 GPU 서버 (기존 방식, 제일 빠름)
    - transformers: aarch64+CUDA 서버 (ctranslate2가 GPU CUDA wheel을 안 만들어서 대체)
    두 엔진 모두 동일한 .transcribe() 인터페이스를 제공하므로 호출부 코드는 그대로 재사용됨.
    adapter_path는 transformers 엔진에서만 의미 있음 (LoRA 검증용, 평소엔 None).
    """
    if STT_ENGINE == "transformers":
        from .services.whisper_engine import TransformersWhisperEngine
        return TransformersWhisperEngine(model_id, device=DEVICE, adapter_path=adapter_path)

    from faster_whisper import WhisperModel
    return WhisperModel(model_id, device=DEVICE, compute_type=COMPUTE_TYPE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버 시작 시 STT/화자분리 모델을 GPU 메모리에 한 번만 로드.
    요청마다 모델을 새로 로드하던 기존 subprocess 방식 대비 핵심 성능 개선 지점.
    """
    logger.info(f"🧠 STT 모델 로딩 중... 엔진={STT_ENGINE} / 모델={WHISPER_MODEL_PRECISE} / {DEVICE}")
    app.state.stt_model = _load_whisper_model(WHISPER_MODEL_PRECISE, adapter_path=LORA_ADAPTER_PATH)
    logger.info("✅ STT (정밀/확정용) 모델 로딩 완료")

    # 실시간 회의 STT용 Fast Pass 모델 (2-pass 구조, 저지연 초안 전사 담당)
    logger.info(f"🧠 STT 모델 로딩 중... 엔진={STT_ENGINE} / 모델={WHISPER_MODEL_FAST} / {DEVICE}")
    app.state.stt_model_fast = _load_whisper_model(WHISPER_MODEL_FAST)
    logger.info("✅ STT (실시간/초안용) 모델 로딩 완료")

    logger.info("🧠 pyannote 화자 분리 파이프라인 로딩 중...")
    app.state.diarize_pipeline = Pipeline.from_pretrained(
        DIARIZATION_MODEL, token=HF_TOKEN
    )
    if DEVICE == "cuda":
        import torch
        app.state.diarize_pipeline.to(torch.device("cuda"))
    logger.info("✅ pyannote 파이프라인 로딩 완료")

    logger.info("🧠 화자 임베딩 모델 로딩 중... (실시간 화자 식별용)")
    app.state.speaker_embedding_inference = load_speaker_embedding_inference()
    logger.info("✅ 화자 임베딩 모델 로딩 완료")

    # 회의 시작 전 사전 등록된 화자 프로필 임시 저장소: {session_id: {화자이름: 임베딩}}
    # /api/enroll에서 채워지고, 실시간 WebSocket 세션이 참조. 회의 정상 종료(end) 시 정리됨.
    # enrolled_at은 등록만 하고 방치된 세션의 TTL 정리용 타임스탬프.
    app.state.enrolled_profiles = {}
    app.state.enrolled_at = {}

    # 전역 목소리 프로필 (최초 1회 등록, 디스크 영구 보관) — /api/profiles로 관리,
    # WebSocket attendees 파라미터로 회의마다 재사용
    app.state.voice_profiles = GlobalProfileStore()

    # 진행 중인 실시간 세션 레지스트리: {session_id: RealtimeSTTSession}
    # rename API가 저장소뿐 아니라 살아있는 회의에도 이름 수정을 전파하기 위해 필요
    app.state.active_sessions = {}

    # 실시간 회의 레지스트리 (한 대의 PC 모드/각자 PC 모드 공통) —
    # active_recorders: {session_id: MeetingRecord} — 회의 하나당 recorder 하나. 각자
    #   PC 모드는 여러 참가자가 이 recorder를 공유해 세그먼트를 한 타임라인으로 합침.
    # active_participants: {session_id: {참가자키: None(연결됨) | asyncio.Task(끊김,
    #   재연결 유예 대기 중)}} — 한 대의 PC 모드는 참가자키가 고정값("__solo__") 하나뿐인
    #   그룹처럼 취급. 마지막 참가자가 진짜로 나갈 때만(유예 시간 초과 포함) 회의를
    #   종료(finalize)함 — 이 참조 카운트가 재연결 지원의 핵심 (routers/realtime.py 참고).
    app.state.active_recorders = {}
    app.state.active_participants = {}

    yield  # 서버 동작

    logger.info("🛑 서버 종료, 모델 메모리 해제")


app = FastAPI(
    title="비고 프로젝트 음성 분석 API",
    description="faster-whisper + pyannote 화자 분리 병렬 파이프라인 (GPU 서버용)",
    version="5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영 시 프론트엔드 도메인으로 변경
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.include_router(stt.router, prefix="/api", tags=["Audio Processing"])
app.include_router(realtime.router, prefix="/api", tags=["Realtime STT"])
app.include_router(enroll.router, prefix="/api", tags=["Speaker Enrollment"])
app.include_router(meetings.router, prefix="/api", tags=["Meeting Records"])
app.include_router(profiles.router, prefix="/api", tags=["Global Voice Profiles"])

# 저장된 회의 오디오 원본을 재생/다운로드할 수 있게 정적 서빙 (C-4 및 향후 "다시 듣기" UI용)
app.mount("/meetings-files", StaticFiles(directory=MEETINGS_DIR), name="meetings_files")

# 실시간 STT WebSocket 파이프라인 수동 검증용 테스트 페이지 (정식 프론트엔드 아님)
_TEST_CLIENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_client")
app.mount("/test", StaticFiles(directory=_TEST_CLIENT_DIR, html=True), name="test_client")


@app.get("/")
async def root():
    """서버 정상 작동 확인용 헬스체크 엔드포인트"""
    return {"message": "비고 프로젝트 STT 서버가 정상적으로 실행 중입니다! 🚀"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=False)