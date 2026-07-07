import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

interface User {
  userId: string;
  name: string;
  role : "member" | "lawyer" | "admin";
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  login: (userId: string, password: string) => Promise<void>;
  signup: (userId: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (params: UpdateProfileParams) => Promise<void>;  
  loading: boolean;
  error: string | null;
}

interface UpdateProfileParams{
  name?: string;
  currentPassword ? : string;
  newPassword ? : string;
}
const AuthContext = createContext<AuthContextType | undefined>(undefined);

const BASE_URL = import.meta.env.VITE_API_URL;
const USER_KEY = "agentra-user";
const ACCESS_TOKEN_KEY = "agentra-access-token";
const REFRESH_TOKEN_KEY = "agentra-refresh-token";

// ── 토큰 저장/조회/삭제 ──────────────────────────────────────
const saveTokens = (accessToken: string, refreshToken?: string) => {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
};

const clearTokens = () => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
};

export const getAccessToken = () => localStorage.getItem(ACCESS_TOKEN_KEY);
export const getRefreshToken = () => localStorage.getItem(REFRESH_TOKEN_KEY);

// ── Access Token 갱신 ─────────────────────────────────────────
export const refreshAccessToken = async (): Promise<string | null> => {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  try {
    const res = await fetch(`${BASE_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    const data = await res.json();

    if (data.status === "success" && data.token?.access_token) {
      // Refresh Token은 기존 값 유지 (재발급 안 함)
      saveTokens(data.token.access_token);
      return data.token.access_token;
    }
    // refresh_token_expired 또는 invalid → 로그아웃
    clearTokens();
    return null;
  } catch {
    return null;
  }
};

// ── 인증이 필요한 API 호출 유틸 ──────────────────────────────
// fetch 대신 이 함수 쓰면 토큰 자동 첨부 + 만료 시 자동 갱신
export const authFetch = async (
  url: string,
  options: RequestInit = {}
): Promise<Response> => {
  const token = getAccessToken();

  const makeRequest = (accessToken: string | null) =>
    fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(options.headers ?? {}),
      },
    });

  let res = await makeRequest(token);

  // 401이면 Access Token 만료 → 갱신 후 재시도
  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      res = await makeRequest(newToken);
    } else {
      // Refresh Token도 만료 → 로그인 페이지로
      clearTokens();
      window.location.href = "/login";
    }
  }

  return res;
};

// ── 비밀번호 정책 검사 ────────────────────────────────────────
// 8자 이상, 72bytes 이하, 2종류 이상 조합
export const validatePassword = (pw: string): string | null => {
  if (pw.length < 8) return "비밀번호는 8자 이상이어야 해요";
  if (new Blob([pw]).size > 72) return "비밀번호가 너무 길어요";
  const types = [
    /[A-Z]/.test(pw),
    /[a-z]/.test(pw),
    /[0-9]/.test(pw),
    /[^A-Za-z0-9]/.test(pw),
  ].filter(Boolean).length;
  if (types < 2) return "영문 대/소문자, 숫자, 특수문자 중 2종류 이상 조합해야 해요";
  return null;
};

// ── 로그인 API ───────────────────────────────────────────────
// 요청: { user_id, user_password }
// 응답: { status, user: { user_id, name, role, ... }, token: { access_token, refresh_token, ... } }
async function fetchLogin(userId: string, password: string): Promise<User> {
  const res = await fetch(`${BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, user_password: password }),
  });
  const data = await res.json();

  if (!res.ok || data.status === "error") {
    throw new Error(data.message ?? "로그인에 실패했습니다");
  }

  // 토큰 저장 (access + refresh 둘 다)
  saveTokens(data.token.access_token, data.token.refresh_token);

  return {
    userId: data.user.user_id,
    name: data.user.name,
    role: data.user.role,
  };
}

// ── 회원가입 API ─────────────────────────────────────────────
// 요청: { user_id, user_password, name, role: "lawyer" }
// 응답: { status, user: { user_id, name, ... } } - 토큰 없음
// 가입 후 fetchLogin으로 자동 로그인 처리
async function fetchSignup(userId: string, password: string, name: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      user_password: password,
      name,
      role: "lawyer", // 변호사 앱이므로 lawyer로 고정
    }),
  });
  const data = await res.json();

  if (!res.ok || data.status === "error") {
    throw new Error(data.message ?? "회원가입에 실패했습니다");
  }
  // 응답에 토큰 없음 - 이후 fetchLogin에서 토큰 받음
}

// ── 로그아웃 API ─────────────────────────────────────────────
// refreshToken은 파라미터로 받지 않고 함수 내부에서 조회
// (AuthContext 인터페이스와 시그니처를 맞추고, authFetch가 토큰을
//  들고 있는 상태에서 호출되도록 하기 위함)
async function fetchLogout(): Promise<void> {
  const refreshToken = getRefreshToken();

  // 애초에 refresh token이 없으면 서버 호출 없이 종료
  if (!refreshToken) return;

  const res = await authFetch(`${BASE_URL}/api/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      refresh_token: refreshToken, // 오타 수정: refresh_Token → refresh_token
    }),
  });
  const data = await res.json();

  if (!res.ok || data.status === "error") {
    throw new Error(data.message ?? "로그아웃에 실패했습니다");
  }
}

// ── 사용자 정보 조회 API ─────────────────────────────────────────────
async function fetchProfile(): Promise<User> {
  const res = await authFetch(`${BASE_URL}/api/auth/profile`, {
    method: "GET",
  });
  const data = await res.json();

  if (!res.ok || data.status === "error") {
    throw new Error(data.detail ?? "사용자 정보를 불러오지 못했습니다");
  }
  return {
    userId: data.user.user_id,
    name: data.user.name,
    role: data.user.role,
  };
}


// ── 사용자 정보 수정 API ─────────────────────────────────────────────
async function fetchUpdateProfile(params: UpdateProfileParams): Promise<User> {
  const {name, currentPassword, newPassword} = params;

  if(newPassword) {
    const pwError = validatePassword(newPassword);
    if(pwError) throw new Error(pwError);
    if(!currentPassword){
      throw new Error("비밀번호 변경 시 현재 비밀번호가 필요합니다");
    }
  }

  const body : Record<string, string> = {};
  if(name !== undefined) body.name =name;
  if(currentPassword !== undefined) body.current_password = currentPassword;
  if(newPassword !== undefined) body.new_password = newPassword;

  const res = await authFetch(`${BASE_URL}/api/auth/profile`,
    {
      method :"PATCH",
      headers: { "Content-Type": "application/json" },
      body : JSON.stringify(body),
    });
    const data = await res.json();

    if(!res.ok){
      throw new Error(data.detail ?? "회원 정보 수정에 실패했습니다");
    }
    return {
        userId: data.user.user_id,
        name: data.user.name,
        role: data.user.role,
    };
}

// ── Provider ─────────────────────────────────────────────────
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    // localStorage 값이 손상돼 있어도 앱이 죽지 않도록 try/catch로 감쌈
    try {
      const saved = localStorage.getItem(USER_KEY);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

   useEffect(() => {
    if (!getAccessToken()) return; // 토큰 자체가 없으면 확인할 필요도 없음 (비로그인 상태)

    fetchProfile()
      .then((freshUser) => {
        setUser(freshUser);
        localStorage.setItem(USER_KEY, JSON.stringify(freshUser));
      })
      .catch(() => {
        setUser(null);
        clearTokens();
      });
  }, []);

  const login = async (userId: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      const loggedInUser = await fetchLogin(userId, password);
      setUser(loggedInUser);
      localStorage.setItem(USER_KEY, JSON.stringify(loggedInUser));
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // 회원가입 후 자동 로그인
  const signup = async (userId: string, password: string, name: string) => {
    setLoading(true);
    setError(null);
    try {
      await fetchSignup(userId, password, name);
      // 가입 완료 후 바로 로그인해서 토큰 받기
      const loggedInUser = await fetchLogin(userId, password);
      setUser(loggedInUser);
      localStorage.setItem(USER_KEY, JSON.stringify(loggedInUser));
    } catch (err) {
      setError(err instanceof Error ? err.message : "회원가입에 실패했습니다");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  // 인터페이스 시그니처(() => Promise<void>)와 일치시킴
  // 토큰을 먼저 지우지 않고, 서버 로그아웃 요청을 먼저 시도한 뒤
  // 성공하든 실패하든 마지막에 로컬 상태/토큰을 정리함
  const logout = async () => {
    try {
      await fetchLogout();
    } catch {
      // 서버 로그아웃이 실패해도 로컬 세션은 정리해야 하므로 무시
    } finally {
      setUser(null);
      clearTokens();
    }
  };

  const updateProfile = async (params: UpdateProfileParams) => {
  setLoading(true);
  setError(null);
  try {
    const updatedUser = await fetchUpdateProfile(params);
    setUser(updatedUser);
    localStorage.setItem(USER_KEY, JSON.stringify(updatedUser));
  } catch (err) {
    setError(err instanceof Error ? err.message : "회원 정보 수정에 실패했습니다");
    throw err;
  } finally {
    setLoading(false);
  }
};

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: !!user, login, signup, logout, updateProfile, loading, error }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth는 AuthProvider 내부에서만 사용할 수 있습니다");
  return context;
}