# backend/schemas/auth_schema.py

"""
회원가입, 로그인, 토큰, 프로필과 관련된 Pydantic 스키마를 정의한다.

TODO:
- auth_router.py와 auth_service.py를 Re:Call 인증 구조로 마이그레이션
- 마이그레이션 완료 후 Legacy 블록 삭제
"""

from datetime import datetime
from typing import Optional
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

class SignupRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        title="id",
        description="로그인에 사용할 아이디",
    )
    email: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="이메일",
    )
    password: str = Field(
        ...,
        description="비밀번호",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="화면에 표시할 이름",
    )
    invite_token: Optional[str] = None


class LoginRequest(BaseModel):
    username: str = Field(
        ...,
        title="id",
        description="로그인 아이디",
    )
    password: str = Field(
        ...,
        description="비밀번호",
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
    display_name: Optional[str] = Field(
        default=None,
        description="변경할 표시 이름",
    )
    current_password: Optional[str] = Field(
        default=None,
        description="현재 비밀번호",
    )
    new_password: Optional[str] = Field(
        default=None,
        description="새 비밀번호",
    )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int = 900


class SignupResponse(BaseModel):
    status: str
    user: Optional["UserPublicSchema"] = None
    message: str
    error: Optional[str] = None
    invite_status: Optional[str] = None


class LoginResponse(BaseModel):
    status: str
    user: Optional["UserPublicSchema"] = None
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
    user: Optional["UserPublicSchema"] = None
    message: str
    error: Optional[str] = None


class CheckUserIdResponse(BaseModel):
    """아이디 중복 검사 API 응답 스키마."""

    status: str
    username: str
    available: bool
    message: str
    error: Optional[str] = None

# =============================================================================
# Re:Call: 신규 인증 API 요청/응답
# =============================================================================

class EmailCheckResponse(BaseModel):
    status: str
    email: str
    available: bool
    message: str
    error: Optional[str] = None


class PasswordResetRequestRequest(BaseModel):
    email: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="비밀번호 재설정 링크를 받을 이메일",
    )


class PasswordResetRequestResponse(BaseModel):
    status: str
    message: str
    error: Optional[str] = None


class PasswordResetConfirmRequest(BaseModel):
    reset_token: str = Field(
        ...,
        description="이메일로 받은 비밀번호 재설정 토큰",
    )
    new_password: str = Field(
        ...,
        description="새 비밀번호",
    )


class PasswordResetConfirmResponse(BaseModel):
    status: str
    message: str
    error: Optional[str] = None


class AccountDeleteRequest(BaseModel):
    current_password: str = Field(
        ...,
        description="본인 확인용 현재 비밀번호",
    )


class AccountDeleteResponse(BaseModel):
    status: str
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

class UserPublicSchema(ORMBaseSchema):
    """API 응답 등 외부에 노출할 수 있는 사용자 스키마."""

    id: UUID
    username: str
    email: str
    display_name: str
    profile_image_url: Optional[str] = None
    account_status: AccountStatus
    last_login_at: Optional[datetime] = None
    created_at: datetime

class VoiceProfileResponse(BaseModel):
    registered: bool
    registered_at: Optional[datetime] = None
    speaker_name: Optional[str] = None
    name_extraction_failed: bool = False
    detected_text: Optional[str] = None