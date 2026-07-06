# backend/db/database.py
# SQLite 데이터베이스 연결 및 초기화

import sqlite3
from pathlib import Path

from backend.core.config import settings


DB_PATH = Path(settings.SQLITE_DB_PATH)


def get_connection():
    db_path = Path(settings.SQLITE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 0. users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL UNIQUE,
        user_password   TEXT NOT NULL,
        name            TEXT NOT NULL,
        role            TEXT NOT NULL DEFAULT 'member',
        created_at      TEXT NOT NULL,
        last_login_at   TEXT
    )
    """)

    # 1. conversations
    # user_id에는 로그인 아이디가 아니라 users.id 값을 문자열로 저장
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id         TEXT PRIMARY KEY,
        user_id    TEXT,
        title      TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # 2. messages
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id              TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        role            TEXT NOT NULL,
        content         TEXT NOT NULL,
        source          TEXT DEFAULT 'text',
        created_at      TEXT NOT NULL
    )
    """)

    # 3. summaries
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS summaries (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        summary         TEXT NOT NULL,
        token_count     INTEGER,
        created_at      TEXT NOT NULL
    )
    """)

    # 4. important_facts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS important_facts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL,
        fact            TEXT NOT NULL,
        category        TEXT,
        created_at      TEXT NOT NULL
    )
    """)

    # 5. documents
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id               TEXT PRIMARY KEY,
        conversation_id  TEXT NOT NULL,
        title            TEXT NOT NULL,
        type             TEXT NOT NULL,
        source           TEXT NOT NULL,
        file_path        TEXT,
        json_path        TEXT DEFAULT '',
        content_markdown TEXT DEFAULT '',
        summary          TEXT,
        status           TEXT DEFAULT 'uploaded',
        chroma_status    TEXT DEFAULT 'pending',
        notion_url       TEXT,
        error            TEXT,
        metadata         TEXT DEFAULT '{}',
        created_at       TEXT NOT NULL
    )
    """)

    # 6. tasks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id              TEXT PRIMARY KEY,
        document_id     TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        task            TEXT NOT NULL,
        assignee        TEXT,
        deadline        TEXT,
        status          TEXT DEFAULT 'todo',
        priority        TEXT DEFAULT 'medium',
        created_at      TEXT NOT NULL
    )
    """)

    # 7. document_chunks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_chunks (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id  TEXT NOT NULL,
        chunk_index  INTEGER NOT NULL,
        content      TEXT NOT NULL,
        start_time   REAL,
        end_time     REAL,
        speaker      TEXT,
        content_type TEXT DEFAULT 'transcription',
        user_edited  INTEGER DEFAULT 0,
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )
    """)

    # 8. room_document_links
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS room_document_links (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id     TEXT NOT NULL,
        document_id TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        UNIQUE(room_id, document_id)
    )
    """)

    # 9. indexes
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_conversations_user_id
    ON conversations(user_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
    ON messages(conversation_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_documents_conversation_id
    ON documents(conversation_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_tasks_conversation_id
    ON tasks(conversation_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_tasks_document_id
    ON tasks(document_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
    ON document_chunks(document_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_room_document_links_room_id
    ON room_document_links(room_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_room_document_links_document_id
    ON room_document_links(document_id)
    """)

    # ── 마이그레이션: 기존 DB에 컬럼/테이블 없을 때 자동 추가 ──
    migrations = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT NOT NULL UNIQUE,
            user_password   TEXT NOT NULL,
            name            TEXT NOT NULL,
            role            TEXT NOT NULL DEFAULT 'member',
            created_at      TEXT NOT NULL,
            last_login_at   TEXT
        )
        """,
        "ALTER TABLE conversations ADD COLUMN user_id TEXT",
        "ALTER TABLE documents ADD COLUMN json_path TEXT DEFAULT ''",
        "ALTER TABLE documents ADD COLUMN content_markdown TEXT DEFAULT ''",
        "ALTER TABLE documents ADD COLUMN metadata TEXT DEFAULT '{}'",
        "ALTER TABLE documents ADD COLUMN chroma_status TEXT DEFAULT 'pending'",
        "ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'medium'",
        """
        CREATE TABLE IF NOT EXISTS room_document_links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id     TEXT NOT NULL,
            document_id TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            UNIQUE(room_id, document_id)
        )
        """,
    ]

    for sql in migrations:
        try:
            cursor.execute(sql)
            print(f"[migration] 적용: {sql.strip()[:60]}...")
        except sqlite3.OperationalError as e:
            # 이미 존재하는 컬럼이면 무시
            if "duplicate column name" in str(e).lower():
                pass
            else:
                print(f"[migration] 건너뜀: {sql.strip()[:60]}... / {e}")
        except Exception as e:
            print(f"[migration] 실패: {sql.strip()[:60]}... / {e}")

    conn.commit()
    conn.close()

    print("DB 초기화 완료:", settings.SQLITE_DB_PATH)


if __name__ == "__main__":
    init_db()