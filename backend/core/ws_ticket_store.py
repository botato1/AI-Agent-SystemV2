# backend/core/ws_ticket_store.py

"""
WebSocket 티켓 1회 사용 추적 (메모리 기반, 단일 서버 프로세스 전제).
서버를 여러 대로 늘리면 Redis 등 공유 저장소로 교체 필요.
"""

import time

_used_tickets: dict[str, float] = {}  # jti -> 만료 시각(unix timestamp)


def _cleanup_expired() -> None:
    now = time.time()
    expired = [jti for jti, exp in _used_tickets.items() if exp < now]
    for jti in expired:
        _used_tickets.pop(jti, None)


def consume_ticket(jti: str, expires_at: float) -> bool:
    """처음 쓰는 티켓이면 사용 처리하고 True, 이미 썼으면 False."""
    _cleanup_expired()
    if jti in _used_tickets:
        return False
    _used_tickets[jti] = expires_at
    return True