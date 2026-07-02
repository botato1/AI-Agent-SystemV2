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

// TODO: 지수님 백엔드 인증 엔드포인트 나오면 이 함수만 교체
async function fetchLogin(userId: string, password: string): Promise<User> {
  await new Promise((resolve) => setTimeout(resolve, 500));

  if (!userId || !password) {
    throw new Error("아이디와 비밀번호를 입력해주세요");
  }

  return { userId, name: userId };
}

// TODO: 회원가입 엔드포인트 나오면 이 함수도 같이 교체
// 회원가입은 로그인 상태를 만들지 않음 - 가입만 하고 별도로 로그인하도록 유도
async function fetchSignup(userId: string, password: string, name: string): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));

  if (!userId || !password || !name) {
    throw new Error("모든 항목을 입력해주세요");
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

  // 가입만 하고 로그인 상태로 만들지 않음 - 호출부(SignupPage)에서 /login으로 이동시킴
  const signup = async (userId: string, password: string, name: string) => {
    setLoading(true);
    setError(null);
    try {
      await fetchSignup(userId, password, name);
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
  if (!context) {
    throw new Error("useAuth는 AuthProvider 내부에서만 사용할 수 있습니다");
  }
  return context;
}