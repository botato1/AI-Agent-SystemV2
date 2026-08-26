# backend/main.py

from fastapi import FastAPI

from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio

from backend.db.base import init_db
from backend.routers.chat_router import router as chat_router
from backend.routers.rag_router import router as rag_router
from backend.routers.document_ws_router import router as document_ws_router
from backend.routers.document_router import router as document_router
from backend.routers.task_router import router as task_router
from backend.routers.auth_router import router as auth_router
from backend.routers.workspace_router import router as workspace_router
from backend.routers.meeting_router import router as meeting_router, decisions_router as decisions_router
from backend.routers.meeting_ws_router import router as meeting_ws_router
from backend.routers.room_ws_router import router as room_ws_router
from backend.routers.contradiction_router import router as contradiction_router
from backend.routers.worktree_router import router as worktree_router
from backend.routers.ai_chat_router import router as ai_chat_router, standalone_router as ai_chat_standalone_router
from backend.routers.notification_router import router as notification_router
from backend.routers.notification_router import router as notification_router, preferences_router as notification_preferences_router
from backend.routers.dashboard_router import router as dashboard_router
from backend.routers.webhook_router import router as webhook_router
from backend.routers.category_router import router as category_router, item_router as category_item_router
from backend.modules.rag.chroma_client import warm_up_reranker
from fastapi.middleware.cors import CORSMiddleware

from backend.services.auth_service import PROFILE_IMAGE_STORAGE_DIR
from backend.services.meeting_reminder_service import check_and_send_meeting_reminders

app = FastAPI(
    title="AI-Agent-System Backend",
    description="FastAPI backend for AI Agent System",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://192.168.0.23:5173", "http://61.81.98.82:3000","http://192.168.0.7:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 서버 실행 시 PostgreSQL 테이블 자동 생성 (개발용, 운영은 Alembic 권장)
init_db()

PROFILE_IMAGE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/profile_images", StaticFiles(directory=PROFILE_IMAGE_STORAGE_DIR), name="profile_images")

# 서버 시작 시 리랭커 모델 미리 로딩
warm_up_reranker()

async def _meeting_reminder_loop():
    while True:
        await asyncio.to_thread(check_and_send_meeting_reminders)
        await asyncio.sleep(60)

@app.on_event("startup")
async def _start_meeting_reminder_loop():
    asyncio.create_task(_meeting_reminder_loop())

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(rag_router)
app.include_router(document_ws_router)
app.include_router(document_router)
app.include_router(task_router)
app.include_router(workspace_router)
app.include_router(meeting_router)
app.include_router(decisions_router)
app.include_router(meeting_ws_router)
app.include_router(room_ws_router)
app.include_router(contradiction_router)
app.include_router(worktree_router)
app.include_router(ai_chat_router)
app.include_router(ai_chat_standalone_router)
app.include_router(notification_router)
app.include_router(notification_preferences_router)
app.include_router(dashboard_router)
app.include_router(webhook_router)
app.include_router(category_router)
app.include_router(category_item_router)

@app.get("/")
def root():
    return {
        "message" : "AI-Agent-System backend is running"
    }