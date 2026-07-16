# backend/main.py

from fastapi import FastAPI

from backend.db.base import init_db
from backend.routers.chat_router import router as chat_router
from backend.routers.rag_router import router as rag_router
from backend.routers.document_router import router as document_router
from backend.routers.task_router import router as task_router
from backend.routers.stt_router import router as stt_router
from backend.routers.auth_router import router as auth_router
from backend.modules.rag.chroma_client import warm_up_reranker
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI-Agent-System Backend",
    description="FastAPI backend for AI Agent System",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 서버 실행 시 PostgreSQL 테이블 자동 생성 (개발용, 운영은 Alembic 권장)
init_db()

# 서버 시작 시 리랭커 모델 미리 로딩
warm_up_reranker()

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(rag_router)
app.include_router(document_router)
app.include_router(task_router)
app.include_router(stt_router)

@app.get("/")
def root():
    return {
        "message" : "AI-Agent-System backend is running"
    }