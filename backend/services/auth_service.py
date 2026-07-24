# backend/services/auth_service.py

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
    TokenResponse,
    UserPublicSchema,
    CheckUserIdResponse,
    EmailCheckResponse,
    PasswordResetRequestRequest,
    PasswordResetRequestResponse,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    AccountDeleteRequest,
    AccountDeleteResponse,
)

from backend.db.crud import auth_crud

from backend.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    get_user_id_from_access_token,
    get_user_id_from_refresh_token,
    hash_token,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_password_reset_token,
    verify_password_reset_token,
    password_fingerprint,
)

from backend.core.config import settings
from backend.core.email import send_password_reset_email

def _create_token_response(db: Session, user_id: UUID) -> TokenResponse:
    access_token = create_access_token(user_id=str(user_id))
    refresh_token = create_refresh_token(user_id=str(user_id))

    auth_crud.store_refresh_token(
        db,
        user_id=user_id,
        token_hash=hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _normalize_and_validate_username(username: str) -> str:
    normalized = username.strip()

    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="아이디는 공백일 수 없습니다.",
        )

    if len(normalized) > 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="아이디는 50자 이하만 사용할 수 있습니다.",
        )

    return normalized


def _validate_password_format(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호는 8자 이상이어야 합니다.",
        )

    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="비밀번호는 72 bytes 이하만 사용할 수 있습니다.",
        )

    categories = 0

    if any(char.isupper() for char in password):
        categories += 1
    if any(char.islower() for char in password):
        categories += 1
    if any(char.isdigit() for char in password):
        categories += 1
    if any(not char.isalnum() for char in password):
        categories += 1

    if categories < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "비밀번호는 영문 대문자, 영문 소문자, 숫자, "
                "특수문자 중 2종류 이상을 조합해야 합니다."
            ),
        )


def _has_profile_update_fields(request: ProfileUpdateRequest) -> bool:
    return request.display_name is not None or request.new_password is not None


# 아이디 중복 확인
def check_user_id_available(db: Session, username: str) -> CheckUserIdResponse:
    normalized_username = _normalize_and_validate_username(username)

    exists = auth_crud.get_user_by_username(db, normalized_username) is not None

    return CheckUserIdResponse(
        status="success",
        username=normalized_username,
        available=not exists,
        message="이미 사용 중인 아이디입니다." if exists else "사용 가능한 아이디입니다.",
        error=None,
    )


# 회원가입 처리
def signup(db: Session, request: SignupRequest) -> SignupResponse:
    normalized_username = _normalize_and_validate_username(request.username)

    if auth_crud.get_user_by_username(db, normalized_username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 아이디입니다.",
        )

    if auth_crud.get_user_by_email(db, request.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일입니다.",
        )

    _validate_password_format(request.password)

    password_hash = hash_password(request.password)

    try:
        user = auth_crud.create_user(
            db,
            username=normalized_username,
            email=request.email,
            display_name=request.display_name,
            password_hash=password_hash,
            account_status="active",
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 아이디 또는 이메일입니다.",
        )

    return SignupResponse(
        status="success",
        user=UserPublicSchema.model_validate(user),
        message="회원가입이 완료되었습니다.",
        error=None,
    )


# 로그인 처리
def login(db: Session, request: LoginRequest) -> LoginResponse:
    normalized_username = _normalize_and_validate_username(request.username)

    user = auth_crud.get_user_by_username(db, normalized_username)

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    auth_crud.update_user_last_login(db, user.id)

    refreshed_user = auth_crud.get_user_by_id(db, user.id) or user

    return LoginResponse(
        status="success",
        user=UserPublicSchema.model_validate(refreshed_user),
        token=_create_token_response(db, refreshed_user.id),
        message="로그인에 성공했습니다.",
        error=None,
    )


# Refresh Token으로 Access Token 재발급
def refresh_access_token(db: Session, request: RefreshTokenRequest) -> RefreshTokenResponse:
    try:
        user_pk = get_user_id_from_refresh_token(request.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Refresh Token입니다.",
        )

    token_row = auth_crud.get_refresh_token_by_hash(db, hash_token(request.refresh_token))

    if not token_row or token_row.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="무효화된 Refresh Token입니다.",
        )

    if token_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="만료된 Refresh Token입니다.",
        )

    user = auth_crud.get_user_by_id(db, UUID(user_pk))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    access_token = create_access_token(user_id=str(user.id))

    return RefreshTokenResponse(
        status="success",
        token=TokenResponse(
            access_token=access_token,
            refresh_token=None,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
        message="Access Token이 재발급되었습니다.",
        error=None,
    )


# 로그아웃 처리 - refresh_tokens를 실제로 revoke한다
def logout(db: Session, request: LogoutRequest) -> LogoutResponse:
    if request.refresh_token:
        auth_crud.revoke_refresh_token(db, hash_token(request.refresh_token))

    return LogoutResponse(
        status="success",
        message="로그아웃이 완료되었습니다.",
        error=None,
    )


def get_profile(db: Session, access_token: str) -> ProfileResponse:
    try:
        user_pk = get_user_id_from_access_token(access_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Access Token입니다.",
        )

    user = auth_crud.get_user_by_id(db, UUID(user_pk))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return ProfileResponse(
        status="success",
        user=UserPublicSchema.model_validate(user),
        message="사용자 정보를 조회했습니다.",
        error=None,
    )


def update_profile(db: Session, access_token: str, request: ProfileUpdateRequest) -> ProfileResponse:
    try:
        user_pk = get_user_id_from_access_token(access_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Access Token입니다.",
        )

    if not _has_profile_update_fields(request):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="수정할 회원 정보가 없습니다.",
        )

    user = auth_crud.get_user_by_id(db, UUID(user_pk))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    if request.display_name is not None:
        display_name = request.display_name.strip()

        if not display_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이름은 빈 값으로 수정할 수 없습니다.",
            )

        auth_crud.update_user_profile(db, user.id, display_name=display_name)

    if request.new_password is not None:
        if not request.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="비밀번호 변경 시 현재 비밀번호가 필요합니다.",
            )

        _validate_password_format(request.new_password)

        if not verify_password(request.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="현재 비밀번호가 올바르지 않습니다.",
            )

        auth_crud.update_user_password(db, user.id, hash_password(request.new_password))

    updated_user = auth_crud.get_user_by_id(db, user.id)

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return ProfileResponse(
        status="success",
        user=UserPublicSchema.model_validate(updated_user),
        message="사용자 정보가 수정되었습니다.",
        error=None,
    )

# 이메일 중복 확인
def check_email_available(db: Session, email: str) -> EmailCheckResponse:
    exists = auth_crud.get_user_by_email(db, email) is not None

    return EmailCheckResponse(
        status="success",
        email=email,
        available=not exists,
        message="이미 사용 중인 이메일입니다." if exists else "사용 가능한 이메일입니다.",
        error=None,
    )


# 비밀번호 재설정 요청 - 계정 존재 여부와 무관하게 항상 동일한 응답
def request_password_reset(db: Session, request: PasswordResetRequestRequest) -> PasswordResetRequestResponse:
    user = auth_crud.get_user_by_email(db, request.email)

    if user:
        reset_token = create_password_reset_token(str(user.id), user.password_hash)
        send_password_reset_email(user.email, reset_token)

    return PasswordResetRequestResponse(
        status="success",
        message="입력하신 이메일로 비밀번호 재설정 링크를 발송했습니다. (계정이 존재하는 경우)",
        error=None,
    )


# 비밀번호 재설정 확인 - 지문 비교로 재사용 차단, 성공 시 기존 세션 전부 로그아웃
def confirm_password_reset(db: Session, request: PasswordResetConfirmRequest) -> PasswordResetConfirmResponse:
    try:
        payload = verify_password_reset_token(request.reset_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 재설정 링크입니다.",
        )

    user = auth_crud.get_user_by_id(db, UUID(payload["sub"]))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    # 토큰 발급 이후 비밀번호가 이미 바뀌었다면(=이미 이 토큰으로 재설정했다면) 재사용 차단
    if payload.get("pwd_fp") != password_fingerprint(user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이미 사용되었거나 만료된 재설정 링크입니다.",
        )

    _validate_password_format(request.new_password)

    auth_crud.update_user_password(db, user.id, hash_password(request.new_password))
    auth_crud.revoke_all_refresh_tokens_for_user(db, user.id)

    return PasswordResetConfirmResponse(
        status="success",
        message="비밀번호가 재설정되었습니다. 다시 로그인해주세요.",
        error=None,
    )


# 회원 탈퇴 - 소프트 삭제 + 기존 세션 전부 로그아웃
def delete_account(db: Session, access_token: str, request: AccountDeleteRequest) -> AccountDeleteResponse:
    try:
        user_pk = get_user_id_from_access_token(access_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Access Token입니다.",
        )

    user = auth_crud.get_user_by_id(db, UUID(user_pk))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="비밀번호가 올바르지 않습니다.",
        )

    auth_crud.revoke_all_refresh_tokens_for_user(db, user.id)
    auth_crud.soft_delete_user(db, user.id)

    return AccountDeleteResponse(
        status="success",
        message="회원 탈퇴가 완료되었습니다.",
        error=None,
    )