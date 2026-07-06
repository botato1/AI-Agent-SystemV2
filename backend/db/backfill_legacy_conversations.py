# backend/db/backfill_legacy_conversations.py

import sys

from backend.db.database import get_connection


def backfill_legacy_conversations(owner_user_id: str) -> int:
    """
    Auth 도입 전 생성되어 user_id가 NULL인 기존 채팅방을
    특정 사용자에게 수동 이관한다.

    주의:
    - 운영 환경에서 자동 실행하지 않는다.
    - 데이터 소유자가 명확한 개발/테스트 데이터에만 사용한다.
    - owner_user_id는 users.id 값을 문자열로 넣는다.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE id = ?", (owner_user_id,))
    if cursor.fetchone() is None:
        conn.close()
        raise ValueError(f"users.id={owner_user_id} 에 해당하는 사용자가 없습니다.")

    cursor.execute("""
        UPDATE conversations
        SET user_id = ?
        WHERE user_id IS NULL
    """, (str(owner_user_id),))

    updated_count = cursor.rowcount

    conn.commit()
    conn.close()

    return updated_count


def _count_legacy_conversations() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM conversations WHERE user_id IS NULL")
    count = cursor.fetchone()[0]
    conn.close()
    return count


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python -m backend.db.backfill_legacy_conversations <users.id>")
        sys.exit(1)

    owner_user_id = sys.argv[1]

    legacy_count = _count_legacy_conversations()

    if legacy_count == 0:
        print("[backfill] 이관할 user_id=NULL 채팅방이 없습니다.")
        sys.exit(0)

    confirm = input(
        f"user_id=NULL 채팅방 {legacy_count}개를 users.id={owner_user_id}로 "
        f"이관합니다. 계속하시겠습니까? (y/N): "
    )
    if confirm.strip().lower() != "y":
        print("취소되었습니다.")
        sys.exit(0)

    try:
        updated_count = backfill_legacy_conversations(owner_user_id)
    except ValueError as e:
        print(f"[backfill] 실패: {e}")
        sys.exit(1)

    print(
        f"[backfill] user_id=NULL 기존 채팅방 {updated_count}개를 "
        f"users.id={owner_user_id}로 이관했습니다."
    )

    # TODO: access_logs 스키마 확정 후 이관 기록 추가
    # (resource_type='conversation', action='backfill_ownership' 등)