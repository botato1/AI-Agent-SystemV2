const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// 로그인 API 응답 타입
export interface LoginResponse {
  status: "success" | "error";
  user: {
    id: string;
    username: string;
    email: string;
    display_name: string;
    account_status: string;
    last_login_at: string;
    created_at: string;
  } | null;
  token: {
    access_token: string;
    refresh_token: string | null;
    token_type: string;
    expires_in: number;
  } | null;
  message: string;
  error: string | null;
  detail?: string;
}

// Refresh API 응답 타입
export interface RefreshResponse {
  status: "success" | "error";
  token: {
    access_token: string;
    refresh_token: string | null;
    token_type: string;
    expires_in: number;
  } | null;
  message: string;
  error: string | null;
  detail?: string;
}

// 프로필 조회 및 수정 응답 타입
export interface ProfileResponse {
  status: "success" | "error";
  user: {
    id: string;
    username: string;
    email: string;
    display_name: string;
    account_status: string;
    last_login_at: string;
    created_at: string;
  } | null;
  message: string;
  error: string | null;
  detail?: string; // 💡 타입 에러 해결을 위해 detail 속성 추가
}

// 프로필 수정 요청 파라미터 타입
export interface UpdateProfileParams {
  displayName?: string;
  currentPassword?: string;
  newPassword?: string;
}

// 1. 아이디 중복 확인 (GET /api/auth/check-user-id)
export async function checkUserId(username: string): Promise<{ isAvailable: boolean; message: string }> {
  const trimmedUsername = username.trim();
  const hasKorean = /[ㄱ-ㅎ|ㅏ-ㅣ|가-힣]/.test(trimmedUsername);
  if (hasKorean) {
    return { isAvailable: false, message: "아이디에는 한글을 사용할 수 없어요." };
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/check-user-id?username=${encodeURIComponent(trimmedUsername)}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    const contentType = response.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
      return { isAvailable: false, message: "서버 응답 오류가 발생했습니다." };
    }

    const data = await response.json();

    if (!data.available) {
      return { isAvailable: false, message: "이미 사용 중인 아이디예요." };
    }

    return { isAvailable: true, message: data.message || "사용 가능한 아이디예요." };
  } catch (error) {
    console.error("checkUserId error:", error);
    return { isAvailable: false, message: "네트워크 연결 상태를 확인해 주세요." };
  }
}

// 2. 이메일 중복 확인 (GET /api/auth/check-email)
export async function checkEmail(email: string): Promise<{ isAvailable: boolean; message: string }> {
  const trimmedEmail = email.trim();

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(trimmedEmail)) {
    return { isAvailable: false, message: "올바른 이메일 형식이 아닙니다." };
  }

  if (trimmedEmail.length > 255) {
    return { isAvailable: false, message: "이메일은 255자 이내로 입력해 주세요." };
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/check-email?email=${encodeURIComponent(trimmedEmail)}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    const data = await response.json();

    if (response.status === 422) {
      return { isAvailable: false, message: data.message || "이메일 형식이 올바르지 않습니다." };
    }

    if (!response.ok) {
      return { isAvailable: false, message: "이메일 중복 확인 중 오류가 발생했습니다." };
    }

    return {
      isAvailable: data.available,
      message: data.message || "사용 가능한 이메일입니다.",
    };
  } catch (error) {
    console.error("checkEmail error:", error);
    return { isAvailable: false, message: "네트워크 연결 상태를 확인해 주세요." };
  }
}

// 3. 로그인 API (POST /api/auth/login)
export async function loginApi(username: string, password: string): Promise<LoginResponse> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        username: username.trim(),
        password: password.trim(),
      }),
    });

    const data: LoginResponse = await response.json();

    if (!response.ok || data.status === "error") {
      return {
        status: "error",
        user: null,
        token: null,
        message: data.message || data.detail || "아이디 또는 비밀번호가 올바르지 않습니다.",
        error: data.error || "UNAUTHORIZED",
      };
    }

    return data;
  } catch (error) {
    console.error("loginApi error:", error);
    return {
      status: "error",
      user: null,
      token: null,
      message: "서버와 통신할 수 없습니다. 네트워크를 확인해 주세요.",
      error: "NETWORK_ERROR",
    };
  }
}

// 4. 회원가입 API (POST /api/auth/signup)
export async function signUpApi(params: {
  username: string;
  email: string;
  password: string;
  displayName: string;
}) {
  try {
    const payload = {
      username: params.username.trim(),
      email: params.email.trim(),
      password: params.password.trim(),
      display_name: params.displayName.trim(),
      name: params.displayName.trim(),
    };

    const response = await fetch(`${API_BASE_URL}/api/auth/signup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      console.error("회원가입 에러 상세:", data);
      return {
        status: "error",
        message: data.message || data.detail || "회원가입 처리 중 오류가 발생했습니다.",
      };
    }

    return {
      status: "success",
      message: data.message || "회원가입이 완료되었습니다.",
      data,
    };
  } catch (error) {
    console.error("signUpApi 통신 error:", error);
    return {
      status: "error",
      message: "서버 연결에 실패했습니다. 네트워크 상태를 확인해 주세요.",
    };
  }
}

// 5. Access Token 재발급 API (POST /api/auth/refresh)
export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token");

  if (!refreshToken) {
    console.warn("Refresh Token이 존재하지 않습니다.");
    return null;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        refresh_token: refreshToken,
      }),
    });

    const data: RefreshResponse = await response.json();

    if (!response.ok || data.status === "error" || !data.token) {
      console.error("토큰 재발급 실패:", data.message);
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      return null;
    }

    const newAccessToken = data.token.access_token;
    localStorage.setItem("access_token", newAccessToken);

    if (data.token.refresh_token) {
      localStorage.setItem("refresh_token", data.token.refresh_token);
    }

    return newAccessToken;
  } catch (error) {
    console.error("refreshAccessToken 통신 오류:", error);
    return null;
  }
}

// 6. 인증이 필요한 요청에 사용하는 Auto-Refresh Fetch 래퍼
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  let accessToken = localStorage.getItem("access_token");

  const headers = new Headers(options.headers || {});
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    console.log("Access Token 만료. 재발급 시도 중...");
    const newAccessToken = await refreshAccessToken();

    if (newAccessToken) {
      headers.set("Authorization", `Bearer ${newAccessToken}`);
      response = await fetch(url, { ...options, headers });
    } else {
      window.location.href = "/";
    }
  }

  return response;
}

// 7. 로그아웃 API (POST /api/auth/logout)
export async function logoutApi(): Promise<void> {
  const refreshToken = localStorage.getItem("refresh_token");
  const accessToken = localStorage.getItem("access_token");

  try {
    await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({
        refresh_token: refreshToken || undefined,
      }),
    });
  } catch (error) {
    console.error("logoutApi error:", error);
  } finally {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }
}

// 8. 사용자 정보 조회 API (GET /api/auth/profile)
export async function getProfileApi(): Promise<ProfileResponse> {
  try {
    const response = await authFetch(`${API_BASE_URL}/api/auth/profile`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    const data: ProfileResponse = await response.json();

    if (!response.ok || data.status === "error") {
      return {
        status: "error",
        user: null,
        message: data.message || data.detail || "사용자 정보를 가져오지 못했습니다.",
        error: data.error || "UNAUTHORIZED",
      };
    }

    return data;
  } catch (error) {
    console.error("getProfileApi error:", error);
    return {
      status: "error",
      user: null,
      message: "서버와 통신 중 오류가 발생했습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

// 9. 사용자 정보 수정 API (PATCH /api/auth/profile)
export async function updateProfileApi(params: UpdateProfileParams): Promise<ProfileResponse> {
  const payload: Record<string, string> = {};
  if (params.displayName !== undefined) {
    payload.display_name = params.displayName.trim();
  }
  if (params.currentPassword) {
    payload.current_password = params.currentPassword;
  }
  if (params.newPassword) {
    payload.new_password = params.newPassword;
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/auth/profile`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data: ProfileResponse = await response.json();

    if (!response.ok || data.status === "error") {
      let customMessage = data.message || data.detail;

      if (response.status === 401) {
        customMessage = customMessage || "현재 비밀번호가 일치하지 않습니다. 다시 확인해 주세요.";
      } else if (response.status === 400) {
        customMessage = customMessage || "입력한 비밀번호 형식이 올바르지 않거나 필수 항목이 누락되었습니다.";
      }

      return {
        status: "error",
        user: null,
        message: customMessage || "프로필 수정에 실패했습니다.",
        error: data.error || "UPDATE_FAILED",
      };
    }

    return data;
  } catch (error) {
    console.error("updateProfileApi error:", error);
    return {
      status: "error",
      user: null,
      message: "서버와 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.",
      error: "NETWORK_ERROR",
    };
  }
}

// 비밀번호 재설정 요청 API 응답 타입
export interface PasswordResetRequestResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

// 10. 비밀번호 재설정 요청 API (POST /api/auth/password-reset/request)
export async function requestPasswordResetApi(email: string): Promise<PasswordResetRequestResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || '';
  const trimmedEmail = email.trim();

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/password-reset/request`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        email: trimmedEmail,
      }),
    });

    const data = await response.json();

    // 422 Unprocessable Entity (이메일 누락 / 형식 오류)
    if (response.status === 422) {
      return {
        status: "error",
        message: data.message || data.detail?.[0]?.msg || "올바른 이메일 형식을 입력해 주세요.",
        error: "UNPROCESSABLE_ENTITY",
      };
    }

    if (!response.ok || data.status === "error") {
      return {
        status: "error",
        message: data.message || "비밀번호 재설정 요청 중 오류가 발생했습니다.",
        error: data.error || "REQUEST_FAILED",
      };
    }

    return {
      status: "success",
      message: data.message || "입력하신 이메일로 비밀번호 재설정 링크를 발송했습니다. (계정이 존재하는 경우)",
      error: null,
    };
  } catch (error) {
    console.error("requestPasswordResetApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다. 네트워크 상태를 확인해 주세요.",
      error: "NETWORK_ERROR",
    };
  }
}

// 비밀번호 재설정 확인 API 응답 타입
export interface PasswordResetConfirmResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

// 11. 비밀번호 재설정 확인 API (POST /api/auth/password-reset/confirm)
export async function confirmPasswordResetApi(
  resetToken: string,
  newPassword: string
): Promise<PasswordResetConfirmResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || '';

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/password-reset/confirm`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        reset_token: resetToken.trim(),
        new_password: newPassword,
      }),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "비밀번호 재설정에 실패했습니다.";
      
      // 상태 코드별 예외 메시지 정돈
      if (response.status === 400) {
        defaultMsg = "새 비밀번호가 보안 정책에 맞지 않습니다.";
      } else if (response.status === 401) {
        defaultMsg = "유효하지 않거나 만료된 재설정 토큰입니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 사용자입니다.";
      }

      return {
        status: "error",
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      message: data.message || "비밀번호가 재설정되었습니다. 다시 로그인해주세요.",
      error: null,
    };
  } catch (error) {
    console.error("confirmPasswordResetApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다. 네트워크 상태를 확인해 주세요.",
      error: "NETWORK_ERROR",
    };
  }
}

// 회원 탈퇴 API 응답 타입
export interface DeleteAccountResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

// 12. 회원 탈퇴 API (DELETE /api/auth/account)
export async function deleteAccountApi(currentPassword: string): Promise<DeleteAccountResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || '';
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/account`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        current_password: currentPassword,
      }),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회원 탈퇴 처리 중 오류가 발생했습니다.";
      if (response.status === 401) {
        defaultMsg = "현재 비밀번호가 일치하지 않거나 인증이 만료되었습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 사용자입니다.";
      }

      return {
        status: "error",
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    // 탈퇴 성공 시 저장된 토큰 정리
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");

    return {
      status: "success",
      message: data.message || "회원 탈퇴가 완료되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("deleteAccountApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다. 네트워크 상태를 확인해 주세요.",
      error: "NETWORK_ERROR",
    };
  }
}