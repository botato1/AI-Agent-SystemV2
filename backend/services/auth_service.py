from fastapi import HTTPException, status
from jose import JWTError

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
    UserResponse,
)

from backend.db.crud import (
    create_user,
    get_user_by_user_id,
    get_user_by_id,
    update_user_profile,
    update_user_password,
    update_user_last_login,
)

from backend.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    get_user_id_from_access_token,
    get_user_id_from_refresh_token,
)

from backend.core.config import settings


# DB user row를 API 응답용 UserResponse로 변환
def _to_user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=user.get("id"),
        user_id=user.get("user_id") or "",
        name=user.get("name") or "",
        role=user.get("role") or "member",
        created_at=user.get("created_at"),
        last_login_at=user.get("last_login_at"),
    )


# Access Token / Refresh Token 응답 생성
def _create_token_response(user_id: str, role: str = "member") -> TokenResponse:
    access_token = create_access_token(user_id=user_id, role=role)
    refresh_token = create_refresh_token(user_id=user_id, role=role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

# 비밀번호 형식을 검증
# 조건 : 8자 이상, 72 bytes 이하, 영문 대문자 / 소문자 / 숫자 / 특수문자 중 2종류 이상 조합
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
            detail="비밀번호는 영문 대문자, 영문 소문자, 숫자, 특수문자 중 2종류 이상을 조합해야 합니다.",
        )

# 프로필 수정 요청에 실제 수정할 값이 있는지 확인
def _has_profile_update_fields(request: ProfileUpdateRequest) -> bool:
    return request.name is not None or request.new_password is not None


# 회원가입 처리
def signup(request: SignupRequest) -> SignupResponse:
    existing_user = get_user_by_user_id(request.user_id)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 아이디입니다.",
        )

    _validate_password_format(request.user_password)

    password_hash = hash_password(request.user_password)

    user = create_user(
        user_id=request.user_id,
        user_password=password_hash,
        name=request.name,
        role=request.role,
    )

    return SignupResponse(
        status="success",
        user=_to_user_response(user),
        message="회원가입이 완료되었습니다.",
        error=None,
    )


# 로그인 처리
def login(request: LoginRequest) -> LoginResponse:
    user = get_user_by_user_id(request.user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    password_hash = user.get("user_password")

    if not password_hash or not verify_password(request.user_password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    update_user_last_login(user["id"])

    # last_login_at 갱신 후 최신 사용자 정보 다시 조회
    refreshed_user = get_user_by_id(user["id"]) or user

    return LoginResponse(
        status="success",
        user=_to_user_response(refreshed_user),
        token=_create_token_response(
            user_id=str(refreshed_user["id"]),
            role=refreshed_user.get("role") or "member",
        ),
        message="로그인에 성공했습니다.",
        error=None,
    )


# Refresh Token으로 Access Token 재발급
def refresh_access_token(request: RefreshTokenRequest) -> RefreshTokenResponse:
    try:
        user_pk = get_user_id_from_refresh_token(request.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Refresh Token입니다.",
        )

    user = get_user_by_id(user_pk)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )

    access_token = create_access_token(
        user_id=str(user["id"]),
        role=user.get("role") or "member",
    )

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


def logout(request: LogoutRequest) -> LogoutResponse:
    """
    현재 구조에서는 JWT를 서버에 저장하지 않으므로,
    로그아웃은 클라이언트가 Access Token / Refresh Token을 삭제하는 방식으로 처리한다.
    """
    return LogoutResponse(
        status="success",
        message="로그아웃이 완료되었습니다.",
        error=None,
    )


def get_profile(access_token: str) -> ProfileResponse:
    try:
        user_pk = get_user_id_from_access_token(access_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Access Token입니다.",
        )

    user = get_user_by_id(user_pk)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return ProfileResponse(
        status="success",
        user=_to_user_response(user),
        message="사용자 정보를 조회했습니다.",
        error=None,
    )


def update_profile(access_token: str, request: ProfileUpdateRequest) -> ProfileResponse:
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

    user = get_user_by_id(user_pk)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    # 이름 수정
    if request.name is not None:
        name = request.name.strip()

        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="이름은 빈 값으로 수정할 수 없습니다.",
            )

        update_user_profile(
            id=user_pk,
            name=name,
        )

    # 비밀번호 수정
    if request.new_password is not None:
        if not request.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="비밀번호 변경 시 현재 비밀번호가 필요합니다.",
            )

        _validate_new_password(request.new_password)

        password_hash = user.get("user_password")

        if not password_hash or not verify_password(request.current_password, password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="현재 비밀번호가 올바르지 않습니다.",
            )

        new_password_hash = hash_password(request.new_password)

        update_user_password(
            id=user_pk,
            user_password=new_password_hash,
        )

    updated_user = get_user_by_id(user_pk)

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    return ProfileResponse(
        status="success",
        user=_to_user_response(updated_user),
        message="사용자 정보가 수정되었습니다.",
        error=None,
    )