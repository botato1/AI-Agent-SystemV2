# backend/routers/auth_router.py

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
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
    EmailCheckResponse,
    PasswordResetRequestRequest,
    PasswordResetRequestResponse,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    AccountDeleteRequest,
    AccountDeleteResponse,
    VoiceProfileResponse,
    RegisteredVoiceProfileListResponse,
)
from backend.services.auth_service import (
    signup,
    login,
    refresh_access_token,
    logout,
    get_profile,
    update_profile,
    update_profile_image,
    check_user_id_available,
    check_email_available,
    request_password_reset,
    confirm_password_reset,
    delete_account,
    get_voice_profile_script,
    list_registered_voice_profiles,
    register_voice_profile,
    get_voice_profile_status,
    rename_voice_profile,
    remove_voice_profile,
    delete_profile_image,
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"],
)


# 회원가입
@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup_api(request: SignupRequest, db: Session = Depends(get_db)):
    return signup(db, request)


# 아이디 중복 확인
@router.get("/check-user-id", response_model=CheckUserIdResponse)
def check_user_id_api(
    username: str = Query(..., min_length=1, max_length=50, title="id"),
    db: Session = Depends(get_db),
):
    return check_user_id_available(db, username)


# 이메일 중복 확인
@router.get("/check-email", response_model=EmailCheckResponse)
def check_email_api(
    email: str = Query(..., min_length=1, max_length=255),
    db: Session = Depends(get_db),
):
    return check_email_available(db, email)


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

# 프로필 이미지 설정/변경 (최초 등록이든 이후 수정이든 동일 엔드포인트)
@router.patch("/profile/image", response_model=ProfileResponse)
async def update_profile_image_api(
    file: UploadFile = File(...),
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    file_content = await file.read()
    return update_profile_image(db, access_token, file.filename, file_content)

# 프로필 이미지 삭제 (기본 색상 아바타로 폴백)
@router.delete("/profile/image", response_model=ProfileResponse)
def delete_profile_image_api(
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    return delete_profile_image(db, access_token)

# 등록용 문장 조회
@router.get("/voice-profile/script")
def get_voice_profile_script_api():
    return {"script": get_voice_profile_script()}

@router.get("/voice-profile/list", response_model=RegisteredVoiceProfileListResponse)
def list_registered_voice_profiles_api():
    return RegisteredVoiceProfileListResponse(names=list_registered_voice_profiles())


# 목소리 등록 (raw PCM16LE 16kHz mono bytes)
@router.post("/voice-profile", response_model=VoiceProfileResponse, status_code=status.HTTP_201_CREATED)
async def register_voice_profile_api(
    request: Request,
    speaker_name: str | None = Query(default=None),
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    audio_bytes = await request.body()
    return register_voice_profile(db, access_token, audio_bytes, speaker_name_override=speaker_name)


@router.get("/voice-profile", response_model=VoiceProfileResponse)
def get_voice_profile_api(
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    return get_voice_profile_status(db, access_token)


# 이름 오인식 시 수정
@router.patch("/voice-profile/rename", response_model=VoiceProfileResponse)
def rename_voice_profile_api(
    new_name: str = Query(...),
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    return rename_voice_profile(db, access_token, new_name)


@router.delete("/voice-profile", response_model=VoiceProfileResponse)
def delete_voice_profile_api(
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    return remove_voice_profile(db, access_token)

# 비밀번호 재설정 요청
@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
def request_password_reset_api(request: PasswordResetRequestRequest, db: Session = Depends(get_db)):
    return request_password_reset(db, request)


# 비밀번호 재설정 확인
@router.post("/password-reset/confirm", response_model=PasswordResetConfirmResponse)
def confirm_password_reset_api(request: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
    return confirm_password_reset(db, request)


# 회원 탈퇴
@router.delete("/account", response_model=AccountDeleteResponse)
def delete_account_api(
    request: AccountDeleteRequest,
    access_token: str = Depends(get_access_token),
    db: Session = Depends(get_db),
):
    return delete_account(db, access_token, request)