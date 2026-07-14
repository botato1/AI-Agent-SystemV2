"""AI Chat (RAG QA) CRUD — 내 파트

room 단위 세션, 사용자별 비공개.
"""

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.modules import AiChatMessage, AiChatSession, AiMessageSource


def get_or_create_session(
    db: Session, workspace_id: uuid.UUID, room_id: uuid.UUID, user_id: uuid.UUID
) -> AiChatSession:
    row = (
        db.query(AiChatSession)
        .filter(
            AiChatSession.workspace_id == workspace_id,
            AiChatSession.room_id == room_id,
            AiChatSession.user_id == user_id,
            AiChatSession.deleted_at.is_(None),
        )
        .first()
    )
    if row:
        return row
    row = AiChatSession(workspace_id=workspace_id, room_id=room_id, user_id=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_message(
    db: Session,
    session_id: uuid.UUID,
    role: str,  # 'user' | 'assistant' | 'system'
    content: str,
    model_name: Optional[str] = None,
) -> AiChatMessage:
    row = AiChatMessage(
        session_id=session_id, role=role, content=content, model_name=model_name
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def add_sources(
    db: Session, ai_message_id: uuid.UUID, sources: list[dict]
) -> list[AiMessageSource]:
    """
    sources 예시:
    [{"source_type": "content_chunk", "file_id": ..., "chunk_id": ..., "similarity_score": 0.82, "display_order": 0}]
    """
    rows = [
        AiMessageSource(ai_message_id=ai_message_id, **s)
        for s in sources
    ]
    db.add_all(rows)
    db.commit()
    for r in rows:
        db.refresh(r)
    return rows


def get_session_history(db: Session, session_id: uuid.UUID) -> list[AiChatMessage]:
    return (
        db.query(AiChatMessage)
        .filter(AiChatMessage.session_id == session_id)
        .order_by(AiChatMessage.created_at)
        .all()
    )


def get_message_sources(db: Session, ai_message_id: uuid.UUID) -> list[AiMessageSource]:
    return (
        db.query(AiMessageSource)
        .filter(AiMessageSource.ai_message_id == ai_message_id)
        .order_by(AiMessageSource.display_order)
        .all()
    )
