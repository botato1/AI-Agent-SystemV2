"""AI Chat (RAG QA) CRUD — 내 파트

room 단위 세션, 사용자별 비공개.
"""

import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
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
    try:
        db.commit()
    except IntegrityError:
        # [수정 사항 - 2026.07.15] 리뷰 피드백 반영: 동시 요청 레이스 컨디션
        # idx_ai_chat_sessions_owner에 unique=True를 추가해 DB 레벨에서
        # 중복 세션 생성을 막았음. 두 요청이 거의 동시에 들어와서 위의
        # SELECT에서는 둘 다 "없음"으로 보고 동시에 INSERT를 시도하면,
        # 둘 중 하나는 unique 제약 위반으로 여기서 실패함 — 그 경우
        # 실패한 쪽은 새로 만들지 않고 이미 만들어진 row를 다시 조회해서 반환.
        db.rollback()
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
        raise

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

# 메시지와 그 페시지가 속한 세션을 함께 조회(소유권 검증용)
def get_message_with_session(
    db: Session, ai_message_id: uuid.UUID
) -> Optional[tuple[AiChatMessage, AiChatSession]]:
    return (
        db.query(AiChatMessage, AiChatSession)
        .join(AiChatSession, AiChatSession.id == AiChatMessage.session_id)
        .filter(AiChatMessage.id == ai_message_id)
        .first()
    )