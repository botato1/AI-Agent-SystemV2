# backend/core/security.py
# 비밀번호 해시, JWT Access Token / Refresh Token 생성 및 검증 유틸

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import hashlib

from jose import JWTError, jwt
from passlib.context import CryptContext

import uuid as uuid_lib

from backend.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

WS_TICKET_EXPIRE_SECONDS = 180
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
ALGORITHM = "HS256"


def _get_secret_key() -> str:
    secret_key = getattr(settings, "JWT_SECRET_KEY", None)

    if not secret_key:
        secret_key = getattr(settings, "SECRET_KEY", None)

    if not secret_key:
        raise RuntimeError(
            "JWT secret key가 설정되지 않았습니다. "
            "settings.JWT_SECRET_KEY 또는 settings.SECRET_KEY를 설정해주세요."
        )

    return secret_key

# 평문 비밀번호를 bcrypt 해시값으로 변환
def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

# 입력된 평문 비밀번호와 DB에 저장된 해시 비밀번호를 비교
def verify_password(plain_password: str, hashed_password: str) -> bool:

    return pwd_context.verify(plain_password, hashed_password)

# Refresh Token 원문을 저장하지 않고 조회/무효화용 해시만 저장하기 위한 함수
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# Access Token 생성 : 기본 만료 시간 = 15분
def create_access_token(user_id: str, role: Optional[str] = None, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "exp": expire,
    }

    if role:
        payload["role"] = role

    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)

# Refresh Token 생성 : 기본 만료 시간 = 7일
def create_refresh_token(user_id: str, role: Optional[str] = None, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "exp": expire,
    }

    if role:
        payload["role"] = role

    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)

# JWT 토큰 검증 및 payload 반환. 토큰이 유효하지 않거나 만료된 경우 JWTError 발생
def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])

# JWT 토큰에서 user_id 추출. user_id는 payload의 sub 값으로 저장
def get_user_id_from_token(token: str) -> str:
    payload = decode_token(token)
    user_id = payload.get("sub")

    if not user_id:
        raise JWTError("토큰에 user_id 정보가 없습니다.")

    return user_id

# Access Token인지 확인 후 payload 반환
def verify_access_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise JWTError("Access Token이 아닙니다.")

    if not payload.get("sub"):
        raise JWTError("토큰에 user_id 정보가 없습니다.")

    return payload

# Refresh Token인지 확인 후 payload 반환
def verify_refresh_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)

    if payload.get("type") != "refresh":
        raise JWTError("Refresh Token이 아닙니다.")

    if not payload.get("sub"):
        raise JWTError("토큰에 user_id 정보가 없습니다.")

    return payload

# Access Token에서 user_id 추출
def get_user_id_from_access_token(token: str) -> str:
    payload = verify_access_token(token)
    return payload["sub"]

# Refresh Token에서 user_id 추출
def get_user_id_from_refresh_token(token: str) -> str:
    payload = verify_refresh_token(token)
    return payload["sub"]

# 비밀번호 해시의 일부를 재설정 토큰에 지문으로 남긴다.
# 비밀번호가 바뀌면 지문도 달라지므로, 이미 사용된(비밀번호가 이미 바뀐)
# reset_token은 검증 시 자동으로 걸러진다 (재사용 방지).
def password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]

# Password Reset Token 생성 : 기본 만료 시간 = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
def create_password_reset_token(
    user_id: str,
    password_hash: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    )

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "password_reset",
        "pwd_fp": password_fingerprint(password_hash),
        "exp": expire,
    }

    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)

# Password Reset Token인지 확인 후 payload 반환
def verify_password_reset_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)

    if payload.get("type") != "password_reset":
        raise JWTError("비밀번호 재설정 토큰이 아닙니다.")

    if not payload.get("sub"):
        raise JWTError("토큰에 user_id 정보가 없습니다.")

    return payload

# Password Reset Token에서 user_id 추출
def get_user_id_from_password_reset_token(token: str) -> str:
    payload = verify_password_reset_token(token)
    return payload["sub"]

# WebSocket 연결용 일회용 티켓 발급 (기본 만료 60초 — 발급 직후 바로 연결한다는 전제)
def create_ws_ticket(user_id: str, meeting_id: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(seconds=WS_TICKET_EXPIRE_SECONDS)
    )

    payload: dict[str, Any] = {
        "sub": user_id,
        "meeting_id": meeting_id,
        "type": "ws_ticket",
        "jti": str(uuid_lib.uuid4()),
        "exp": expire,
    }

    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


# WebSocket 티켓 검증 (type/meeting_id/jti 확인 후 payload 반환)
def verify_ws_ticket(token: str) -> dict[str, Any]:
    payload = decode_token(token)

    if payload.get("type") != "ws_ticket":
        raise JWTError("WebSocket 티켓이 아닙니다.")

    if not payload.get("sub") or not payload.get("meeting_id") or not payload.get("jti"):
        raise JWTError("티켓에 필요한 정보가 없습니다.")

    return payload