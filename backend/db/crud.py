# backend/db/crud.py
import uuid
from datetime import datetime, timezone

from backend.db.database import get_connection


def get_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_conversation_title(content: str, max_length: int = 30) -> str:
    content = (content or "").strip().replace("\n", " ")
    if not content:
        return "새 채팅"
    if len(content) > max_length:
        return content[:max_length] + "..."
    return content

# ==========================================
# 0. users CRUD
# ==========================================

# 회원가입 시 users 테이블에 사용자 정보 저장
# user_password에는 해시된 비밀번호를 저장
def create_user(user_id: str, user_password: str, name: str, role: str = "member") -> dict:
    now = get_utc_now()
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO users (
                user_id,
                user_password,
                name,
                role,
                created_at,
                last_login_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                user_password,
                name,
                role,
                now,
                None,
            ),
        )

        created_id = cursor.lastrowid
        conn.commit()

        return {
            "id": created_id,
            "user_id": user_id,
            "name": name,
            "role": role,
            "created_at": now,
            "last_login_at": None,
        }

    except Exception:
        if conn:
            conn.rollback()
        raise

    finally:
        if conn:
            conn.close()

# 로그인 ID로 사용자를 조회
# 로그인 시 아이디 중복 확인 / 비밀번호 검증에 사용
def get_user_by_user_id(user_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            user_id,
            user_password,
            name,
            role,
            created_at,
            last_login_at
        FROM users
        WHERE user_id = ?
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None

# 내부 사용자 PK(id)로 사용자 조회
# JWT 토큰 검증 후 현재 사용자 정보를 가져올 떄 사용
def get_user_by_id(id: int | str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            user_id,
            user_password,
            name,
            role,
            created_at,
            last_login_at
        FROM users
        WHERE id = ?
        LIMIT 1
        """,
        (id,),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None

# 회원가입 시 user_id 중복 여부를 확인
def is_user_id_exists(user_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM users
        WHERE user_id = ?
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return row is not None

# 사용자 이름을 수정
def update_user_profile(id: int | str, name: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET name = ?
        WHERE id = ?
        """,
        (name, id),
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    return updated > 0

# 사용자 비밀번호 해시를 수정
def update_user_password(id: int | str, user_password: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET user_password = ?
        WHERE id = ?
        """,
        (user_password, id),
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    return updated > 0

# 로그인 성공 시 마지막 로그인 시간을 갱신
def update_user_last_login(id: int | str) -> bool:
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET last_login_at = ?
        WHERE id = ?
        """,
        (now, id),
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    return updated > 0


# ==========================================
# 1. conversations CRUD
# ==========================================

def create_conversation(title: str, user_id: str) -> str:
    conv_id = str(uuid.uuid4())
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO conversations (
            id,
            user_id,
            title,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (conv_id, str(user_id), title, now, now),
    )
    conn.commit()
    conn.close()

    return conv_id

def ensure_conversation(conversation_id: str, user_id: str, title: str = "새 채팅"):
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id
        FROM conversations
        WHERE id = ?
          AND user_id = ?
        """,
        (conversation_id, str(user_id)),
    )

    if cursor.fetchone() is None:
        cursor.execute(
            """
            INSERT INTO conversations (
                id,
                user_id,
                title,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, str(user_id), title, now, now),
        )
    else:
        cursor.execute(
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
              AND user_id = ?
            """,
            (now, conversation_id, str(user_id)),
        )

    conn.commit()
    conn.close()


def update_conversation_timestamp(conversation_id: str, user_id: str) -> bool:
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE conversations
        SET updated_at = ?
        WHERE id = ?
          AND user_id = ?
        """,
        (now, conversation_id, str(user_id)),
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    return updated > 0

def update_conversation_title(conversation_id: str, title: str, user_id: str) -> dict | None:
    now = get_utc_now()
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE conversations
            SET title = ?,
                updated_at = ?
            WHERE id = ?
              AND user_id = ?
            """,
            (title, now, conversation_id, str(user_id)),
        )

        updated = cursor.rowcount
        conn.commit()

        if updated == 0:
            return None

        return {
            "room_id": conversation_id,
            "conversation_id": conversation_id,
            "title": title,
            "updated_at": now,
        }

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[crud] update_conversation_title 실패: {repr(e)}")
        return None

    finally:
        if conn:
            conn.close()

def get_conversations(user_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            c.id,
            c.title,
            c.created_at,
            c.updated_at,
            d.title AS filename,
            d.id AS document_id
        FROM conversations c
        LEFT JOIN documents d
            ON d.id = (
                SELECT d2.id
                FROM documents d2
                WHERE d2.conversation_id = c.id
                ORDER BY d2.created_at DESC
                LIMIT 1
            )
        WHERE c.user_id = ?
        ORDER BY c.updated_at DESC
        """,
        (str(user_id),),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def get_conversation_by_id(room_id: str, user_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, title, created_at, updated_at
        FROM conversations
        WHERE id = ?
          AND user_id = ?
        LIMIT 1
        """,
        (room_id, str(user_id)),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def delete_conversation(room_id: str, user_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id
        FROM conversations
        WHERE id = ?
          AND user_id = ?
        LIMIT 1
        """,
        (room_id, str(user_id)),
    )

    if cursor.fetchone() is None:
        conn.close()
        return False

    cursor.execute(
        """
        DELETE FROM document_chunks
        WHERE document_id IN (
            SELECT id
            FROM documents
            WHERE conversation_id = ?
        )
        """,
        (room_id,),
    )

    cursor.execute(
        """
        DELETE FROM messages
        WHERE conversation_id = ?
        """,
        (room_id,),
    )

    cursor.execute(
        """
        DELETE FROM tasks
        WHERE conversation_id = ?
        """,
        (room_id,),
    )

    cursor.execute(
        """
        DELETE FROM documents
        WHERE conversation_id = ?
        """,
        (room_id,),
    )

    cursor.execute(
        """
        DELETE FROM summaries
        WHERE conversation_id = ?
        """,
        (room_id,),
    )

    cursor.execute(
        """
        DELETE FROM important_facts
        WHERE conversation_id = ?
        """,
        (room_id,),
    )

    cursor.execute(
        """
        DELETE FROM room_document_links
        WHERE room_id = ?
        """,
        (room_id,),
    )

    cursor.execute(
        """
        DELETE FROM conversations
        WHERE id = ?
          AND user_id = ?
        """,
        (room_id, str(user_id)),
    )

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count > 0

def delete_all_conversations_and_messages(user_id: str) -> dict:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM document_chunks
        WHERE document_id IN (
            SELECT d.id
            FROM documents d
            JOIN conversations c ON c.id = d.conversation_id
            WHERE c.user_id = ?
        )
        """,
        (str(user_id),),
    )

    cursor.execute(
        """
        DELETE FROM tasks
        WHERE conversation_id IN (
            SELECT id FROM conversations WHERE user_id = ?
        )
        """,
        (str(user_id),),
    )

    cursor.execute(
        """
        DELETE FROM messages
        WHERE conversation_id IN (
            SELECT id FROM conversations WHERE user_id = ?
        )
        """,
        (str(user_id),),
    )

    cursor.execute(
        """
        DELETE FROM summaries
        WHERE conversation_id IN (
            SELECT id FROM conversations WHERE user_id = ?
        )
        """,
        (str(user_id),),
    )

    cursor.execute(
        """
        DELETE FROM important_facts
        WHERE conversation_id IN (
            SELECT id FROM conversations WHERE user_id = ?
        )
        """,
        (str(user_id),),
    )

    cursor.execute(
        """
        DELETE FROM room_document_links
        WHERE room_id IN (
            SELECT id FROM conversations WHERE user_id = ?
        )
        """,
        (str(user_id),),
    )

    cursor.execute(
        """
        DELETE FROM documents
        WHERE conversation_id IN (
            SELECT id FROM conversations WHERE user_id = ?
        )
        """,
        (str(user_id),),
    )

    cursor.execute(
        """
        DELETE FROM conversations
        WHERE user_id = ?
        """,
        (str(user_id),),
    )

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": "현재 사용자의 모든 채팅방과 메시지를 삭제했습니다.",
    }


# ==========================================
# 2. messages CRUD
# ==========================================

def insert_message(conversation_id: str, role: str, content: str, user_id: str) -> str:
    if not conversation_id:
        raise ValueError("conversation_id가 필요합니다.")

    msg_id = str(uuid.uuid4())
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, user_id
        FROM conversations
        WHERE id = ?
        LIMIT 1
        """,
        (conversation_id,),
    )
    conversation = cursor.fetchone()

    if conversation is not None and str(conversation["user_id"]) != str(user_id):
        conn.close()
        raise PermissionError("채팅방 접근 권한이 없습니다.")

    if conversation is None:
        title = make_conversation_title(content) if role == "user" else "새 채팅"
        cursor.execute(
            """
            INSERT INTO conversations (
                id,
                user_id,
                title,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, str(user_id), title, now, now),
        )

    cursor.execute(
        """
        INSERT INTO messages (
            id,
            conversation_id,
            role,
            content,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (msg_id, conversation_id, role, content, now),
    )

    cursor.execute(
        """
        UPDATE conversations
        SET updated_at = ?
        WHERE id = ?
          AND user_id = ?
        """,
        (now, conversation_id, str(user_id)),
    )

    conn.commit()
    conn.close()

    return msg_id


def get_messages(conversation_id: str, user_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id, m.role, m.content, m.created_at
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        WHERE m.conversation_id = ?
          AND c.user_id = ?
        ORDER BY m.created_at ASC
        """,
        (conversation_id, str(user_id)),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def delete_message(message_id: str, user_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM messages
        WHERE id = ?
          AND conversation_id IN (
              SELECT id
              FROM conversations
              WHERE user_id = ?
          )
        """,
        (message_id, str(user_id)),
    )
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count > 0


# ==========================================
# 3. summaries CRUD
# ==========================================

def insert_summary(conversation_id: str, summary_text: str, token_count: int = None):
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO summaries (
            conversation_id,
            summary,
            token_count,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (conversation_id, summary_text, token_count, now),
    )
    conn.commit()
    conn.close()


def get_latest_summary(conversation_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT summary, token_count, created_at
        FROM summaries
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (conversation_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


# ==========================================
# 4. important_facts CRUD
# ==========================================

def insert_fact(conversation_id: str, fact_text: str, category: str = "환경"):
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO important_facts (
            conversation_id,
            fact,
            category,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (conversation_id, fact_text, category, now),
    )
    conn.commit()
    conn.close()


def get_all_facts(conversation_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT fact, category, created_at
        FROM important_facts
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        """,
        (conversation_id,),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


# ==========================================
# 5. documents CRUD
# ==========================================

def save_document_metadata(doc: dict) -> str:
    doc_id = doc.get("id") or str(uuid.uuid4())
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO documents (
            id,
            conversation_id,
            title,
            type,
            source,
            file_path,
            json_path,
            content_markdown,
            summary,
            status,
            notion_url,
            error,
            metadata,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            conversation_id = excluded.conversation_id,
            title = excluded.title,
            type = excluded.type,
            source = excluded.source,
            file_path = excluded.file_path,
            json_path = excluded.json_path,
            content_markdown = excluded.content_markdown,
            summary = excluded.summary,
            status = excluded.status,
            notion_url = excluded.notion_url,
            error = excluded.error,
            metadata = excluded.metadata,
            created_at = excluded.created_at
        """,
        (
            doc_id,
            doc.get("conversation_id", ""),
            doc.get("title", ""),
            doc.get("type", "document"),
            doc.get("source", ""),
            doc.get("file_path", ""),
            doc.get("json_path", ""),
            doc.get("content_markdown", ""),
            doc.get("summary", ""),
            doc.get("status", "processed"),
            doc.get("notion_url", ""),
            doc.get("error", ""),
            doc.get("metadata", "{}"),
            now,
        ),
    )
    conn.commit()
    conn.close()

    return doc_id


def get_documents(conversation_id: str, user_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            d.id,
            d.title,
            d.type,
            d.source,
            d.summary,
            d.status,
            d.chroma_status,
            d.created_at,
            d.json_path,
            d.metadata
        FROM documents d
        JOIN conversations c ON c.id = d.conversation_id
        WHERE d.conversation_id = ?
          AND c.user_id = ?
        ORDER BY d.created_at DESC
        """,
        (conversation_id, str(user_id)),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def get_documents_for_user(user_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            d.id              AS document_id,
            d.title           AS filename,
            d.conversation_id AS room_id,
            d.conversation_id AS conversation_id,
            d.type,
            d.source,
            d.json_path,
            d.chroma_status,
            d.metadata,
            d.created_at
        FROM documents d
        JOIN conversations c ON c.id = d.conversation_id
        WHERE c.user_id = ?
          AND d.type != 'voice'
        ORDER BY d.created_at DESC
        """,
        (str(user_id),),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def get_document_by_id(document_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            conversation_id,
            title,
            type,
            source,
            file_path,
            json_path,
            content_markdown,
            summary,
            status,
            chroma_status,
            notion_url,
            error,
            metadata,
            created_at
        FROM documents
        WHERE id = ?
        LIMIT 1
        """,
        (document_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_document_by_id_for_user(document_id: str, user_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            d.id,
            d.conversation_id,
            d.title,
            d.type,
            d.source,
            d.file_path,
            d.json_path,
            d.content_markdown,
            d.summary,
            d.status,
            d.chroma_status,
            d.notion_url,
            d.error,
            d.metadata,
            d.created_at
        FROM documents d
        JOIN conversations c ON c.id = d.conversation_id
        WHERE d.id = ?
          AND c.user_id = ?
        LIMIT 1
        """,
        (document_id, str(user_id)),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_all_documents() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id              AS document_id,
            title           AS filename,
            conversation_id AS room_id,
            type,
            json_path,
            chroma_status,
            metadata,
            created_at
        FROM documents
        WHERE type != 'voice'
        ORDER BY created_at DESC
        """
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def get_latest_document_by_conversation(conversation_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, title, json_path, metadata
        FROM documents
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (conversation_id,),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def get_document_by_filename_and_conversation(
    conversation_id: str,
    filename: str,
) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, title, json_path, metadata
        FROM documents
        WHERE conversation_id = ?
          AND title = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (conversation_id, filename),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def _get_voice_documents(conversation_id: str | None = None) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    if conversation_id:
        cursor.execute(
            """
            SELECT
                id,
                conversation_id,
                title,
                type,
                source,
                file_path,
                summary,
                status,
                chroma_status,
                metadata,
                created_at
            FROM documents
            WHERE conversation_id = ?
              AND type = 'voice'
            ORDER BY created_at DESC
            """,
            (conversation_id,),
        )
    else:
        cursor.execute(
            """
            SELECT
                id,
                conversation_id,
                title,
                type,
                source,
                file_path,
                summary,
                status,
                chroma_status,
                metadata,
                created_at
            FROM documents
            WHERE type = 'voice'
            ORDER BY created_at DESC
            """
        )

    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def get_all_voice_documents() -> list[dict]:
    return _get_voice_documents()


def get_voice_documents_for_user(user_id: str) -> list[dict]:
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                d.id,
                d.conversation_id,
                d.title,
                d.type,
                d.source,
                d.file_path,
                d.json_path,
                d.summary,
                d.status,
                d.chroma_status,
                d.error,
                d.metadata,
                d.created_at
            FROM documents d
            JOIN conversations c ON c.id = d.conversation_id
            WHERE c.user_id = ?
              AND d.type = 'voice'
            ORDER BY d.created_at DESC
            """,
            (str(user_id),),
        )
        rows = cursor.fetchall() or []
        return [dict(row) for row in rows]

    except Exception as e:
        print(f"[crud] get_voice_documents_for_user 실패: {repr(e)}")
        return []

    finally:
        if conn:
            conn.close()

def get_voice_documents_by_conversation(conversation_id: str) -> list[dict]:
    return _get_voice_documents(conversation_id=conversation_id)


def delete_document(document_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM documents
        WHERE id = ?
        """,
        (document_id,),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted > 0


def delete_document_for_user(document_id: str, user_id: str) -> bool:
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT d.id
            FROM documents d
            JOIN conversations c ON c.id = d.conversation_id
            WHERE d.id = ?
              AND c.user_id = ?
            LIMIT 1
            """,
            (document_id, str(user_id)),
        )

        if cursor.fetchone() is None:
            return False

        cursor.execute(
            """
            DELETE FROM room_document_links
            WHERE document_id = ?
              AND room_id IN (
                  SELECT id
                  FROM conversations
                  WHERE user_id = ?
              )
            """,
            (document_id, str(user_id)),
        )

        cursor.execute(
            """
            DELETE FROM documents
            WHERE id = ?
              AND conversation_id IN (
                  SELECT id
                  FROM conversations
                  WHERE user_id = ?
              )
            """,
            (document_id, str(user_id)),
        )

        deleted = cursor.rowcount > 0
        conn.commit()

        return deleted

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[crud] delete_document_for_user 실패: {repr(e)}")
        return False

    finally:
        if conn:
            conn.close()

# ==========================================
# 6. tasks CRUD
# ==========================================

def save_tasks(tasks: list, document_id: str, conversation_id: str):
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()

    for task in tasks:
        task_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO tasks (
                id,
                document_id,
                conversation_id,
                task,
                assignee,
                deadline,
                status,
                priority,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                document_id,
                conversation_id,
                task.get("task", ""),
                task.get("assignee", ""),
                task.get("deadline", ""),
                task.get("status", "todo"),
                task.get("priority", "medium"),
                now,
            ),
        )

    conn.commit()
    conn.close()


def create_task(task_data: dict) -> dict:
    task_id = str(uuid.uuid4())
    now = get_utc_now()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (
            id,
            document_id,
            conversation_id,
            task,
            assignee,
            deadline,
            status,
            priority,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            task_data.get("document_id") or "",
            task_data.get("room_id") or task_data.get("conversation_id") or "",
            task_data.get("task", ""),
            task_data.get("assignee"),
            task_data.get("deadline"),
            task_data.get("status", "todo"),
            task_data.get("priority", "medium"),
            now,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "task_id": task_id,
        "task": task_data.get("task", ""),
        "assignee": task_data.get("assignee"),
        "deadline": task_data.get("deadline"),
        "status": task_data.get("status", "todo"),
        "priority": task_data.get("priority", "medium"),
        "room_id": task_data.get("room_id") or task_data.get("conversation_id"),
        "document_id": task_data.get("document_id"),
        "created_at": now,
    }


def get_all_tasks() -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            document_id,
            conversation_id,
            task,
            assignee,
            deadline,
            status,
            priority,
            created_at
        FROM tasks
        ORDER BY created_at DESC
        """
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def get_tasks(conversation_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, task, assignee, deadline, status, priority, created_at
        FROM tasks
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        """,
        (conversation_id,),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def get_tasks_by_document(document_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id, document_id, conversation_id,
            task, assignee, deadline, status, priority, created_at
        FROM tasks
        WHERE document_id = ?
        ORDER BY created_at DESC
        """,
        (document_id,),
    )
    rows = cursor.fetchall() or []
    conn.close()
    return [dict(row) for row in rows]


def update_task_status(task_id: str, status: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tasks
        SET status = ?
        WHERE id = ?
        """,
        (status, task_id),
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    return updated > 0


def update_task_priority(task_id: str, priority: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tasks
        SET priority = ?
        WHERE id = ?
        """,
        (priority, task_id),
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    return updated > 0


def delete_task(task_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM tasks
        WHERE id = ?
        """,
        (task_id,),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted > 0


# ==========================================
# 7. document_chunks CRUD
# ==========================================

def save_document_chunks(document_id: str, transcription: list[dict]) -> int:
    if not document_id or not transcription:
        return 0

    conn = get_connection()
    cursor = conn.cursor()
    saved_count = 0

    for idx, seg in enumerate(transcription):
        content = seg.get("text") or ""
        if not content.strip():
            continue

        cursor.execute(
            """
            INSERT INTO document_chunks (
                document_id,
                chunk_index,
                content,
                start_time,
                end_time,
                speaker,
                content_type,
                user_edited
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                idx,
                content.strip(),
                seg.get("start"),
                seg.get("end"),
                seg.get("speaker"),
                seg.get("content_type", "transcription"),
                1 if seg.get("user_edited") else 0,
            ),
        )
        saved_count += 1

    conn.commit()
    conn.close()

    return saved_count


def get_document_chunks(document_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            document_id,
            chunk_index,
            content,
            start_time,
            end_time,
            speaker,
            content_type,
            user_edited,
            created_at
        FROM document_chunks
        WHERE document_id = ?
        ORDER BY chunk_index ASC
        """,
        (document_id,),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def update_chunk_content(chunk_id: int, new_content: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE document_chunks
        SET content = ?,
            user_edited = 1
        WHERE id = ?
        """,
        (new_content, chunk_id),
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()

    return updated > 0


def delete_document_chunks(document_id: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM document_chunks
        WHERE document_id = ?
        """,
        (document_id,),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted


def update_chroma_status(document_id: str, status: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE documents SET chroma_status = ? WHERE id = ?",
        (status, document_id),
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return updated > 0


def get_documents_by_chroma_status(status: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, conversation_id, title, type, source, json_path, chroma_status, created_at
        FROM documents WHERE chroma_status = ? ORDER BY created_at DESC
        """,
        (status,),
    )
    rows = cursor.fetchall() or []
    conn.close()
    return [dict(row) for row in rows]


# ==========================================
# 8. room_document_links CRUD
# ==========================================

def link_document_to_room(room_id: str, document_id: str, user_id: str) -> bool:
    now = get_utc_now()
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT id
            FROM conversations
            WHERE id = ?
              AND user_id = ?
            LIMIT 1
            """,
            (room_id, str(user_id)),
        )

        if cursor.fetchone() is None:
            return False

        cursor.execute(
            """
            SELECT d.id
            FROM documents d
            JOIN conversations c ON c.id = d.conversation_id
            WHERE d.id = ?
              AND c.user_id = ?
            LIMIT 1
            """,
            (document_id, str(user_id)),
        )

        if cursor.fetchone() is None:
            return False

        cursor.execute(
            """
            INSERT OR IGNORE INTO room_document_links (
                room_id,
                document_id,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (room_id, document_id, now),
        )

        conn.commit()
        return True

    except Exception as e:
        print(f"[link_document_to_room] 오류: {e}")
        return False

    finally:
        conn.close()


def unlink_document_from_room(room_id: str, document_id: str, user_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM room_document_links
        WHERE room_id = ?
          AND document_id = ?
          AND room_id IN (
              SELECT id
              FROM conversations
              WHERE user_id = ?
          )
        """,
        (room_id, document_id, str(user_id)),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted > 0


def get_document_ids_by_room(room_id: str, user_id: str) -> list[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT rdl.document_id
        FROM room_document_links rdl
        JOIN conversations c ON c.id = rdl.room_id
        WHERE rdl.room_id = ?
          AND c.user_id = ?
        ORDER BY rdl.created_at DESC
        """,
        (room_id, str(user_id)),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [row["document_id"] for row in rows]


def get_documents_by_room_id_v2(room_id: str, user_id: str) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT d.id, d.title, d.type, d.source, d.chroma_status, d.created_at
        FROM room_document_links rdl
        JOIN documents d ON d.id = rdl.document_id
        JOIN conversations room_c ON room_c.id = rdl.room_id
        JOIN conversations doc_c ON doc_c.id = d.conversation_id
        WHERE rdl.room_id = ?
          AND room_c.user_id = ?
          AND doc_c.user_id = ?
        ORDER BY rdl.created_at DESC
        """,
        (room_id, str(user_id), str(user_id)),
    )
    rows = cursor.fetchall() or []
    conn.close()

    return [dict(row) for row in rows]


def get_documents_by_room_id(room_id: str, user_id: str) -> list:
    return get_documents_by_room_id_v2(room_id, user_id)


def get_document_by_title_and_room(room_id: str, title: str, user_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT d.id, d.title, d.type, d.source, d.chroma_status, d.created_at
        FROM room_document_links rdl
        JOIN documents d ON d.id = rdl.document_id
        JOIN conversations room_c ON room_c.id = rdl.room_id
        JOIN conversations doc_c ON doc_c.id = d.conversation_id
        WHERE rdl.room_id = ?
          AND room_c.user_id = ?
          AND doc_c.user_id = ?
          AND d.title LIKE ?
        ORDER BY rdl.created_at DESC
        LIMIT 1
        """,
        (room_id, str(user_id), str(user_id), f"%{title}%"),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None