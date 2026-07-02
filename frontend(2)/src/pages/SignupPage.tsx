import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { IconScale, IconCheck, IconX } from "@tabler/icons-react";
import { useAuth } from "../context/AuthContext";

export default function SignupPage() {
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [name, setName] = useState("");
  const [done, setDone] = useState(false);
  const { signup, loading, error } = useAuth();
  const navigate = useNavigate();

  // 비밀번호 확인 칸 입력이 있을 때만 일치 여부 판단 (빈 칸일 땐 표시 안 함)
  const passwordsMatch =
    passwordConfirm.length > 0 ? password === passwordConfirm : null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (passwordsMatch === false) return;

    try {
      await signup(userId, password, name);
      setDone(true);
      // 가입 완료 메시지를 잠깐 보여준 뒤 로그인 페이지로 이동
      setTimeout(() => navigate("/login"), 1200);
    } catch {
      // error는 AuthContext에서 상태로 관리
    }
  };

  if (done) {
    return (
      <div
        className="flex items-center justify-center min-h-screen"
        style={{ background: "var(--bg-primary)" }}
      >
        <div
          className="flex flex-col items-center gap-3 rounded-xl p-10"
          style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
        >
          <IconCheck size={28} style={{ color: "var(--accent-text)" }} />
          <p style={{ color: "var(--text-primary)" }}>회원가입이 완료됐어요</p>
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            로그인 페이지로 이동합니다...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex items-center justify-center min-h-screen"
      style={{ background: "var(--bg-primary)" }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl p-8 flex flex-col"
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex flex-col items-center gap-2 mb-7">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ background: "var(--bg-elevated)" }}
          >
            <IconScale size={22} stroke={1.8} style={{ color: "var(--accent-text)" }} />
          </div>
          <p className="text-base font-medium" style={{ color: "var(--text-primary)" }}>
            회원가입
          </p>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            법률 AI 워크스페이스를 시작하세요
          </p>
        </div>

        <div className="flex flex-col gap-1 mb-3">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
            이름
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="이름을 입력하세요"
            className="rounded-md px-3 py-2 text-sm outline-none"
            style={{
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
            required
          />
        </div>

        <div className="flex flex-col gap-1 mb-3">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
            아이디
          </label>
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="사용할 아이디를 입력하세요"
            className="rounded-md px-3 py-2 text-sm outline-none"
            style={{
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
            required
          />
        </div>

        <div className="flex flex-col gap-1 mb-3">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
            비밀번호
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호를 입력하세요"
            className="rounded-md px-3 py-2 text-sm outline-none"
            style={{
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
            required
          />
        </div>

        <div className="flex flex-col gap-1 mb-1">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
            비밀번호 확인
          </label>
          <div className="relative">
            <input
              type="password"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              placeholder="비밀번호를 다시 입력하세요"
              className="rounded-md px-3 py-2 text-sm outline-none w-full"
              style={{
                background: "var(--bg-elevated)",
                color: "var(--text-primary)",
                border: `1px solid ${
                  passwordsMatch === false
                    ? "var(--danger)"
                    : passwordsMatch === true
                    ? "var(--accent-text)"
                    : "var(--border)"
                }`,
              }}
              required
            />
            {passwordsMatch !== null && (
              <span
                className="absolute right-3 top-1/2 -translate-y-1/2"
                aria-hidden="true"
              >
                {passwordsMatch ? (
                  <IconCheck size={16} style={{ color: "var(--accent-text)" }} />
                ) : (
                  <IconX size={16} style={{ color: "var(--danger)" }} />
                )}
              </span>
            )}
          </div>
          {passwordsMatch === false && (
            <p className="text-xs mt-1" style={{ color: "var(--danger)" }}>
              비밀번호가 일치하지 않습니다
            </p>
          )}
          {passwordsMatch === true && (
            <p className="text-xs mt-1" style={{ color: "var(--accent-text)" }}>
              비밀번호가 일치합니다
            </p>
          )}
        </div>

        {error && (
          <p className="text-sm mt-2" style={{ color: "var(--danger)" }}>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || passwordsMatch === false}
          className="rounded-md py-2.5 text-sm font-medium transition-opacity disabled:opacity-50 mt-4"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          {loading ? "가입 중..." : "회원가입"}
        </button>

        <p className="text-center text-sm mt-5" style={{ color: "var(--text-secondary)" }}>
          이미 계정이 있으신가요?{" "}
          <Link to="/login" style={{ color: "var(--accent-text)", fontWeight: 500 }}>
            로그인
          </Link>
        </p>
      </form>
    </div>
  );
}