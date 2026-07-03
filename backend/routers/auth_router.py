# backend/routers/auth_router.py

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.schemas.auth_schema import (
    SignupRequest,
    LoginRequest,
    RefreshTokenRequest,
    LogoutRequest,
    ProfileUpdateRequest,
    SignupResponse,
    LoginResponse,
    RefreshTokenResponse,
    LogoutResponse,
    ProfileResponse,
)
from backend.services.auth_service import (
    signup,
    login,
    refresh_access_token,
    logout,
    get_profile,
    update_profile,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"],
)

security = HTTPBearer()

def get_access_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    return credentials.credentials

# 회원가입
@router.post("/signup", response_model=SignupResponse)
def signup_api(request: SignupRequest):
    return signup(request)

# 로그인
@router.post("/login", response_model=LoginResponse)
def login_api(request: LoginRequest):
    return login(request)

# Refresh Token으로 Access Token 재발급
@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_api(request: RefreshTokenRequest):
    return refresh_access_token(request)

# 로그아웃
@router.post("/logout", response_model=LogoutResponse)
def logout_api(request: LogoutRequest):
    """
    현재 구조에서는 서버가 JWT를 저장하지 않으므로
    클라이언트에서 토큰을 삭제하는 방식으로 처리합니다.
    """
    return logout(request)

# 사용자 정보 조회
@router.get("/profile", response_model=ProfileResponse)
def get_profile_api(access_token: str = Depends(get_access_token)):
    return get_profile(access_token)

# 사용자 정보 수정
@router.patch("/profile", response_model=ProfileResponse)
def update_profile_api(
    request: ProfileUpdateRequest,
    access_token: str = Depends(get_access_token),
):
    return update_profile(access_token, request)