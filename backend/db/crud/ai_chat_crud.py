"""AI Chat (RAG QA) CRUD — 내 파트

room 단위 세션, 사용자별 비공개.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.modules import AiChatMessage, AiChatSession, AiMessageSource, Decision, WorkspaceFile

def get_or_create_session(
    db: Session, workspace_id: uuid.UUID, room_id: Optional[uuid.UUID], user_id: uuid.UUID
) -> AiChatSession:
    query = db.query(AiChatSession).filter(
        AiChatSession.workspace_id == workspace_id,
        AiChatSession.user_id == user_id,
        AiChatSession.deleted_at.is_(None),
    )
    query = (
        query.filter(AiChatSession.room_id == room_id)
        if room_id is not None
        else query.filter(AiChatSession.room_id.is_(None))
    )
    row = query.first()
    if row:
        return row

    row = AiChatSession(workspace_id=workspace_id, room_id=room_id, user_id=user_id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = (
            db.query(AiChatSession)
            .filter(
                AiChatSession.workspace_id == workspace_id,
                AiChatSession.user_id == user_id,
                AiChatSession.deleted_at.is_(None),
            )
            .filter(AiChatSession.room_id == room_id if room_id is not None else AiChatSession.room_id.is_(None))
            .first()
        )
        if row:
            return row
        raise

    db.refresh(row)
    return row

def create_session(
    db: Session, workspace_id: uuid.UUID, room_id: Optional[uuid.UUID], user_id: uuid.UUID
) -> AiChatSession:
    row = AiChatSession(workspace_id=workspace_id, room_id=room_id, user_id=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_sessions(
    db: Session, workspace_id: uuid.UUID, room_id: Optional[uuid.UUID], user_id: uuid.UUID
) -> list[AiChatSession]:
    query = db.query(AiChatSession).filter(
        AiChatSession.workspace_id == workspace_id,
        AiChatSession.user_id == user_id,
        AiChatSession.deleted_at.is_(None),
    )
    query = (
        query.filter(AiChatSession.room_id == room_id)
        if room_id is not None
        else query.filter(AiChatSession.room_id.is_(None))
    )
    return query.order_by(AiChatSession.updated_at.desc()).all()


def get_session(db: Session, session_id: uuid.UUID) -> Optional[AiChatSession]:
    return (
        db.query(AiChatSession)
        .filter(AiChatSession.id == session_id, AiChatSession.deleted_at.is_(None))
        .first()
    )


def delete_session(db: Session, session_id: uuid.UUID) -> None:
    row = db.query(AiChatSession).filter(AiChatSession.id == session_id).first()
    if row:
        row.deleted_at = datetime.now(timezone.utc)
        db.commit()


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

def add_ai_exchange(
    db: Session,
    *,
    session_id: uuid.UUID,
    user_content: str,
    assistant_content: str,
    sources: Optional[list[dict]] = None,
    model_name: Optional[str] = None,
) -> AiChatMessage:
    """
    사용자 질문, AI 답변, 답변 근거를 하나의 트랜잭션으로 저장한다.

    사용자 메시지와 AI 답변에 서로 다른 created_at을 명시해
    조회 시 질문이 답변보다 먼저 정렬되도록 한다.
    """

    try:
        session = db.query(AiChatSession).filter(AiChatSession.id == session_id).first()
        if session and not session.title:
            session.title = user_content.strip()[:40]
        if session:
            session.updated_at = datetime.now(timezone.utc)

        user_created_at = datetime.now(timezone.utc)
        assistant_created_at = user_created_at + timedelta(
            microseconds=1
        )

        user_message = AiChatMessage(
            session_id=session_id,
            role="user",
            content=user_content,
            created_at=user_created_at,
        )

        assistant_message = AiChatMessage(
            session_id=session_id,
            role="assistant",
            content=assistant_content,
            model_name=model_name,
            created_at=assistant_created_at,
        )

        db.add_all(
            [
                user_message,
                assistant_message,
            ]
        )

        # assistant_message.id를 출처 FK에 사용하기 위해 flush한다.
        # 아직 commit은 하지 않는다.
        db.flush()

        if sources:
            source_rows = []

            for source in sources:
                source_fields = dict(source)
                source_fields.pop(
                    "ai_message_id",
                    None,
                )

                source_rows.append(
                    AiMessageSource(
                        ai_message_id=assistant_message.id,
                        **source_fields,
                    )
                )

            db.add_all(source_rows)

        db.commit()
        db.refresh(assistant_message)

        return assistant_message

    except Exception:
        db.rollback()
        raise

def get_session_history(db: Session, session_id: uuid.UUID) -> list[AiChatMessage]:
    return (
        db.query(AiChatMessage)
        .filter(AiChatMessage.session_id == session_id)
        .order_by(
            AiChatMessage.created_at.asc(),
            AiChatMessage.id.asc(),
        )
        .all()
    )


def get_message_sources(db: Session, ai_message_id: uuid.UUID) -> list[tuple[AiMessageSource, str | None]]:
    """근거자료 표시 이름을 함께 반환한다.

    [수정] decision 타입 소스는 file_id가 NULL이라, WorkspaceFile만 outerjoin하던
    기존 쿼리에서는 이름이 항상 None으로 나와 프론트가 "결정사항"이라는 구분 안 되는
    라벨만 표시할 수밖에 없었다. Decision도 같이 outerjoin해서, content_chunk/code_fact는
    원본 파일명을, decision은 결정 제목을 이름으로 채운다 (둘 중 하나만 채워지는 배타적
    관계라 coalesce로 안전하게 합칠 수 있다).
    """
    return (
        db.query(
            AiMessageSource,
            func.coalesce(WorkspaceFile.original_filename, Decision.title),
        )
        .outerjoin(WorkspaceFile, AiMessageSource.file_id == WorkspaceFile.id)
        .outerjoin(Decision, AiMessageSource.decision_id == Decision.id)
        .filter(AiMessageSource.ai_message_id == ai_message_id)
        .order_by(AiMessageSource.display_order)
        .all()
    )

def delete_sources_by_file(db: Session, file_id: uuid.UUID) -> int:
    """문서 삭제 시 그 문서를 근거로 저장된 AI Chat 출처 기록을 먼저 지운다.
    content_chunks 하드 삭제 전에 호출 안 하면 FK 위반이 난다."""
    deleted = (
        db.query(AiMessageSource)
        .filter(AiMessageSource.file_id == file_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted

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