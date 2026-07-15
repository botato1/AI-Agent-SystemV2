"""
전체 모델 재수출 — 이 파일을 import하면 Base.metadata에 28개 테이블이 전부 등록된다.

    from backend.db import modules
    modules.Base.metadata.create_all(bind=engine)

FK가 다른 파일의 테이블을 참조해도(예: code.py -> workspace_files) 문제없다.
SQLAlchemy가 문자열 테이블명으로 lazy resolve하기 때문에, 이 파일에서
전체 모델 클래스만 한 번 로드되면 순서와 무관하게 매핑이 완성된다.
"""

from backend.db.base import Base  # noqa: F401

from .auth import RefreshToken, User
from .workspace import Workspace, WorkspaceMember
from .room import Category, Room, RoomMessage
from .file import RoomFileLink, Worktree, WorkspaceFile
from .document import DocumentAnalysis
from .code import CodeAnalysis, CodeFact, CodeSymbol
from .content_chunk import ContentChunk
from .similarity import FileSimilarity
from .meeting import ActionItem, Decision, Meeting, MeetingSegment, MeetingSummary
from .contradiction import ChangeSummaryDraft, Contradiction, ContradictionResolution
from .ai_chat import AiChatMessage, AiChatSession, AiMessageSource
from .notification import Notification

__all__ = [
    "Base",
    "User", "RefreshToken",
    "Workspace", "WorkspaceMember",
    "Category", "Room", "RoomMessage",
    "Worktree", "WorkspaceFile", "RoomFileLink",
    "DocumentAnalysis",
    "CodeAnalysis", "CodeSymbol", "CodeFact",
    "ContentChunk",
    "FileSimilarity",
    "Meeting", "MeetingSegment", "MeetingSummary", "Decision", "ActionItem",
    "Contradiction", "ContradictionResolution", "ChangeSummaryDraft",
    "AiChatSession", "AiChatMessage", "AiMessageSource",
    "Notification",
]
