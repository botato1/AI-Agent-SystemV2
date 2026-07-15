# backend/routers/auth_router.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.core.dependencies import get_access_token
from backend.db.session import get_db
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
    CheckUserIdResponse,
)
from backend.services.auth_service import (
    signup,
    login,
    refresh_access_token,
    logout,
    get_profile,
    update_profile,
    check_user_id_available,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"],
)


# 회원가입
@router.post("/signup", response_model=SignupResponse)
def signup_api(request: SignupRequest, db: Session = Depends(get_db)):
    return signup(db, request)


# 아이디 중복 확인
@router.get("/check-user-id", response_model=CheckUserIdResponse)
def check_user_id_api(
    username: str = Query(..., min_length=1, max_length=50),
    db: Session = Depends(get_db),
):
    return check_user_id_available(db, username)


# 로그인
@router.post("/login", response_model=LoginResponse)
def login_api(request: LoginRequest, db: Session = Depends(get_db)):
    return login(db, request)


# Refresh Token으로 Access Token 재발급
@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_api(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    return refresh_access_token(db, request)


# 로그아웃
@router.post("/logout", response_model=LogoutResponse)
def logout_api(request: LogoutRequest, db: Session = Depends(get_db)):
    return logout(db, request)


# 사용자 정보 조회
@router.get("/profile", response_model=ProfileResponse)
def get_profile_api(
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    return get_profile(db, access_token)


# 사용자 정보 수정
@router.patch("/profile", response_model=ProfileResponse)
def update_profile_api(
    request: ProfileUpdateRequest,
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    return update_profile(db, access_token, request)