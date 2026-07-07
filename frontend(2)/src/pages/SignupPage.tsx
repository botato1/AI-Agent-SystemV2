import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { IconCheck, IconX } from "@tabler/icons-react";
import { useAuth, validatePassword } from "../context/AuthContext";

export default function SignupPage() {
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [name, setName] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const { signup, loading, error } = useAuth();
  const navigate = useNavigate();

  // 비밀번호 확인 일치 여부
  const passwordsMatch = passwordConfirm.length > 0 ? password === passwordConfirm : null;

  // 비밀번호 정책 검사 결과
  const pwError = password.length > 0 ? validatePassword(password) : null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);

    const pwValidation = validatePassword(password);
    if (pwValidation) { setLocalError(pwValidation); return; }
    if (passwordsMatch === false) { setLocalError("비밀번호가 일치하지 않습니다"); return; }

    try {
      await signup(userId, password, name);
      // 회원가입 후 자동 로그인되어 바로 홈으로 이동
      navigate("/");
    } catch {
      // error는 AuthContext에서 상태로 관리
    }
  };

  function ScaleLogo({ size = 44 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 140 140" fill="none">
      <rect x="34" y="124" width="72" height="5" rx="2.5" fill="var(--text-secondary)" opacity="0.9"/>
      <rect x="44" y="118" width="52" height="8" rx="1.5" fill="var(--text-secondary)" opacity="0.75"/>
      <rect x="54" y="110" width="32" height="10" rx="1" fill="var(--text-secondary)" opacity="0.6"/>
      <rect x="67.5" y="20" width="5" height="92" rx="2" fill="var(--text-secondary)" opacity="0.9"/>
      <rect x="64" y="55" width="12" height="8" rx="2" fill="var(--text-secondary)" opacity="0.7"/>
      <rect x="64" y="75" width="12" height="8" rx="2" fill="var(--text-secondary)" opacity="0.7"/>
      <polygon points="70,10 64,22 76,22" fill="var(--text-secondary)" opacity="0.85"/>
      <rect x="16" y="36" width="108" height="4.5" rx="2" fill="var(--text-secondary)" opacity="0.9"/>
      <circle cx="70" cy="38" r="4" fill="var(--bg-secondary,#161616)" stroke="var(--text-secondary)" strokeWidth="2"/>
      <line x1="22" y1="40" x2="14" y2="74" stroke="var(--text-secondary)" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
      <line x1="28" y1="40" x2="28" y2="74" stroke="var(--text-secondary)" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
      <line x1="34" y1="40" x2="42" y2="74" stroke="var(--text-secondary)" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
      <path d="M8 74 C8 74 28 86 48 74" stroke="var(--text-secondary)" strokeWidth="3" fill="none" strokeLinecap="round" opacity="0.9"/>
      <line x1="96" y1="40" x2="88" y2="78" stroke="var(--text-secondary)" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
      <line x1="112" y1="40" x2="112" y2="78" stroke="var(--text-secondary)" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
      <line x1="118" y1="40" x2="126" y2="78" stroke="var(--text-secondary)" strokeWidth="1.5" strokeLinecap="round" opacity="0.7"/>
      <path d="M92 78 C92 78 112 90 132 78" stroke="var(--text-secondary)" strokeWidth="3" fill="none" strokeLinecap="round" opacity="0.9"/>
    </svg>
  )
}

  return (
    <div
      className="flex items-center justify-center min-h-screen"
      style={{ background: "var(--bg-primary)" }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl p-8 flex flex-col"
        style={{ background: "var(--bg-secondary)", border: "1px solid var(--border)" }}
      >
        <div className="flex flex-col items-center gap-2 mb-7">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: "var(--bg-elevated)" }}>
            <ScaleLogo size={44} />
          </div>
          <p className="text-base font-medium" style={{ color: "var(--text-primary)" }}>회원가입</p>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>법률 AI 워크스페이스를 시작하세요</p>
        </div>

        <div className="flex flex-col gap-1 mb-3">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>이름</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="이름을 입력하세요"
            className="rounded-md px-3 py-2 text-sm outline-none"
            style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
            required
          />
        </div>

        <div className="flex flex-col gap-1 mb-3">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>아이디</label>
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="사용할 아이디를 입력하세요"
            className="rounded-md px-3 py-2 text-sm outline-none"
            style={{ background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border)" }}
            required
          />
        </div>

        <div className="flex flex-col gap-1 mb-1">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>비밀번호</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="8자 이상, 2종류 이상 조합"
            className="rounded-md px-3 py-2 text-sm outline-none"
            style={{
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              border: `1px solid ${pwError ? "var(--danger)" : "var(--border)"}`,
            }}
            required
          />
          {pwError && <p className="text-xs mt-0.5" style={{ color: "var(--danger)" }}>{pwError}</p>}
        </div>

        <div className="flex flex-col gap-1 mb-3 mt-2">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>비밀번호 확인</label>
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
                  passwordsMatch === false ? "var(--danger)" :
                  passwordsMatch === true ? "var(--accent-text)" : "var(--border)"
                }`,
              }}
              required
            />
            {passwordsMatch !== null && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2">
                {passwordsMatch
                  ? <IconCheck size={16} style={{ color: "var(--accent-text)" }} />
                  : <IconX size={16} style={{ color: "var(--danger)" }} />
                }
              </span>
            )}
          </div>
          {passwordsMatch === false && <p className="text-xs mt-0.5" style={{ color: "var(--danger)" }}>비밀번호가 일치하지 않습니다</p>}
          {passwordsMatch === true && <p className="text-xs mt-0.5" style={{ color: "var(--accent-text)" }}>비밀번호가 일치합니다</p>}
        </div>

        {(localError || error) && (
          <p className="text-sm mb-3" style={{ color: "var(--danger)" }}>{localError || error}</p>
        )}

        <button
          type="submit"
          disabled={loading || passwordsMatch === false || !!pwError}
          className="rounded-md py-2.5 text-sm font-medium transition-opacity disabled:opacity-50 mt-1"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          {loading ? "가입 중..." : "회원가입"}
        </button>

        <p className="text-center text-sm mt-5" style={{ color: "var(--text-secondary)" }}>
          이미 계정이 있으신가요?{" "}
          <Link to="/login" style={{ color: "var(--accent-text)", fontWeight: 500 }}>로그인</Link>
        </p>
      </form>
    </div>
  );
}