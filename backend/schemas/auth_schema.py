# backend/schemas/auth_schema.py
# 회원가입/로그인/토큰/프로필 관련 Pydantic 스키마

from typing import Literal, Optional

from pydantic import BaseModel, Field


UserRole = Literal["member", "lawyer", "admin"]


class SignupRequest(BaseModel):
    user_id: str = Field(..., description="로그인에 사용할 사용자 아이디")
    user_password: str = Field(..., description="로그인 비밀번호")
    name: str = Field(..., description="사용자 이름")
    role: UserRole = Field(default="member", description="사용자 권한")


class LoginRequest(BaseModel):
    user_id: str = Field(..., description="로그인 아이디")
    user_password: str = Field(..., description="로그인 비밀번호")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Access Token 재발급에 사용할 Refresh Token")


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(default=None, description="무효화할 Refresh Token")


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, description="변경할 사용자 이름")
    current_password: Optional[str] = Field(default=None, description="현재 비밀번호")
    new_password: Optional[str] = Field(default=None, description="새 비밀번호")


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