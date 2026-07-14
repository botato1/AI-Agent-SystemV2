# backend/schemas/auth_schema.py

"""
회원가입, 로그인, 토큰, 프로필과 관련된 Pydantic 스키마를 정의한다.

TODO:
- auth_router.py와 auth_service.py를 Re:Call 인증 구조로 마이그레이션
- SignupRequest, LoginRequest, UserResponse 등 기존 요청·응답 스키마 교체
- users의 기존 UserRole 제거
- 사용자 권한은 workspace_members.role을 기준으로 처리
- 신규 회원가입·로그인 API 스키마는 인증 기능 마이그레이션 시 별도 설계
- 마이그레이션 완료 후 Legacy 블록 삭제
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from backend.schemas.common_schema import (
    ORMBaseSchema,
    SoftDeleteSchema,
    TimestampSchema,
)
from backend.schemas.type_schema import AccountStatus


# =============================================================================
# Legacy: 기존 회원가입·로그인·토큰·프로필 스키마
# =============================================================================

# 기존 인증 코드에서 사용하는 전역 사용자 역할.
# Re:Call에서는 사용자 권한을 workspace_members.role로 관리한다.
UserRole = Literal[
    "member",
    "lawyer",
    "admin",
]


class SignupRequest(BaseModel):
    user_id: str = Field(
        ...,
        description="로그인에 사용할 사용자 아이디",
    )
    user_password: str = Field(
        ...,
        description="로그인 비밀번호",
    )
    name: str = Field(
        ...,
        description="사용자 이름",
    )
    role: UserRole = Field(
        default="member",
        description="사용자 권한",
    )


class LoginRequest(BaseModel):
    user_id: str = Field(
        ...,
        description="로그인 아이디",
    )
    user_password: str = Field(
        ...,
        description="로그인 비밀번호",
    )


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(
        ...,
        description="Access Token 재발급에 사용할 Refresh Token",
    )


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(
        default=None,
        description="무효화할 Refresh Token",
    )


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(
        default=None,
        description="변경할 사용자 이름",
    )
    current_password: Optional[str] = Field(
        default=None,
        description="현재 비밀번호",
    )
    new_password: Optional[str] = Field(
        default=None,
        description="새 비밀번호",
    )


class UserResponse(BaseModel):
    id: int
    user_id: str
    name: str
    role: UserRole
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int = 900


class SignupResponse(BaseModel):
    status: str
    user: Optional[UserResponse] = None
    message: str
    error: Optional[str] = None


class LoginResponse(BaseModel):
    status: str
    user: Optional[UserResponse] = None
    token: Optional[TokenResponse] = None
    message: str
    error: Optional[str] = None


class RefreshTokenResponse(BaseModel):
    status: str
    token: Optional[TokenResponse] = None
    message: str
    error: Optional[str] = None


class LogoutResponse(BaseModel):
    status: str
    message: str
    error: Optional[str] = None


class ProfileResponse(BaseModel):
    status: str
    user: Optional[UserResponse] = None
    message: str
    error: Optional[str] = None


# =============================================================================
# Re:Call: users
# =============================================================================

class UserSchema(TimestampSchema, SoftDeleteSchema):
    """
    사용자 전체 정보를 표현하는 내부 전용 스키마.

    password_hash가 포함되므로 API 응답 모델로 직접 사용하지 않는다.
    외부 응답에는 UserPublicSchema를 사용한다.
    """

    id: UUID
    username: str = Field(
        ...,
        min_length=1,
        max_length=50,
    )
    email: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
    )
    password_hash: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    account_status: AccountStatus = "active"
    last_login_at: Optional[datetime] = None


class UserPublicSchema(ORMBaseSchema):
    """API 응답 등 외부에 노출할 수 있는 사용자 스키마."""

    id: UUID
    username: str
    email: str
    display_name: str
    account_status: AccountStatus
    last_login_at: Optional[datetime] = None
    created_at: datetime


# =============================================================================
# Re:Call: refresh_tokens
# =============================================================================

class RefreshTokenSchema(ORMBaseSchema):
    """
    DB에 저장되는 Refresh Token 정보 스키마.

    원본 Refresh Token은 저장하지 않고 token_hash만 저장한다.
    """

    id: UUID
    user_id: UUID
    token_hash: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    device_info: Optional[str] = Field(
        default=None,
        max_length=255,
    )
    created_at: datetime