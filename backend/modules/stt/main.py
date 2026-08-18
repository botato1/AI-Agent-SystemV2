import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # 💡 추가
import os

from .core.config import logger, UPLOAD_DIR
from .routers import stt

# FastAPI 앱 초기화
app = FastAPI(
    title="비고 프로젝트 음성 분석 API",
    description="Whisper.cpp + Pyannote 화자 분리 하이브리드 파이프라인",
    version="4.0"
)

# CORS 설정 (프론트엔드 연동 시 필수)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영 시에는 프론트엔드 도메인으로 변경
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 💡 핵심: 외부에서 uploads 폴더 내부 파일에 직접 접근할 수 있도록 마운트
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 라우터 등록 (엔드포인트를 /api/v1/stt 형태로 연결)
app.include_router(stt.router, prefix="/api", tags=["Audio Processing"])

@app.get("/")
async def root():
    """서버 정상 작동 확인용 헬스체크 엔드포인트"""
    return {"message": "비고 프로젝트 STT 서버가 정상적으로 실행 중입니다! 🚀"}

if __name__ == "__main__":
    logger.info("서버를 시작합니다...")
    # 개발 모드 실행 (코드 변경 시 자동 재시작)
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)