import { createContext, useContext, useState, type ReactNode } from "react";

interface User {
  userId: string;
  name: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  login: (userId: string, password: string) => Promise<void>;
  signup: (userId: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  loading: boolean;
  error: string | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);
const STORAGE_KEY = "agentra-user";
const BASE_URL = import.meta.env.VITE_API_URL;

// 비밀번호 정책 검사
// 8자 이상, 72bytes 이하, 영문 대/소문자/숫자/특수문자 중 2종류 이상
export const validatePassword = (pw: string): string | null => {
  if (pw.length < 8) return "비밀번호는 8자 이상이어야 해요";
  if (new Blob([pw]).size > 72) return "비밀번호가 너무 길어요";
  const types = [
    /[A-Z]/.test(pw),  // 영문 대문자
    /[a-z]/.test(pw),  // 영문 소문자
    /[0-9]/.test(pw),  // 숫자
    /[^A-Za-z0-9]/.test(pw),  // 특수문자
  ].filter(Boolean).length;
  if (types < 2) return "영문 대/소문자, 숫자, 특수문자 중 2종류 이상 조합해야 해요";
  return null;
};

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
  return { userId: data.user_id ?? userId, name: data.name ?? userId };
}

async function fetchSignup(userId: string, password: string, name: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, user_password: password, name, role: "member" }),
  });
  const data = await res.json();
  if (!res.ok || data.status === "error") {
    throw new Error(data.message ?? "회원가입에 실패했습니다");
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? JSON.parse(saved) : null;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = async (userId: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      const loggedInUser = await fetchLogin(userId, password);
      setUser(loggedInUser);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(loggedInUser));
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
      // 가입 완료 후 바로 로그인
      const loggedInUser = await fetchLogin(userId, password);
      setUser(loggedInUser);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(loggedInUser));
    } catch (err) {
      setError(err instanceof Error ? err.message : "회원가입에 실패했습니다");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  };

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: !!user, login, signup, logout, loading, error }}
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