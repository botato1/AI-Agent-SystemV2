import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

from .core.config import (
    logger, UPLOAD_DIR, DEVICE, COMPUTE_TYPE, WHISPER_MODEL_SIZE,
    DIARIZATION_MODEL, HF_TOKEN
)
from .routers import stt


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    서버 시작 시 STT/화자분리 모델을 GPU 메모리에 한 번만 로드.
    요청마다 모델을 새로 로드하던 기존 subprocess 방식 대비 핵심 성능 개선 지점.
    """
    logger.info(f"🧠 faster-whisper 모델 로딩 중... ({WHISPER_MODEL_SIZE} / {DEVICE} / {COMPUTE_TYPE})")
    app.state.stt_model = WhisperModel(
        WHISPER_MODEL_SIZE,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
    )
    logger.info("✅ faster-whisper 모델 로딩 완료")

    logger.info("🧠 pyannote 화자 분리 파이프라인 로딩 중...")
    app.state.diarize_pipeline = Pipeline.from_pretrained(
        DIARIZATION_MODEL, token=HF_TOKEN
    )
    if DEVICE == "cuda":
        import torch
        app.state.diarize_pipeline.to(torch.device("cuda"))
    logger.info("✅ pyannote 파이프라인 로딩 완료")

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


@app.get("/")
async def root():
    """서버 정상 작동 확인용 헬스체크 엔드포인트"""
    return {"message": "비고 프로젝트 STT 서버가 정상적으로 실행 중입니다! 🚀"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=False)