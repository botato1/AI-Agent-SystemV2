# backend/core/security.py
# 비밀번호 해시, JWT Access Token / Refresh Token 생성 및 검증 유틸

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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