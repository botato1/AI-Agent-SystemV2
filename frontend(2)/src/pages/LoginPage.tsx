import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

type AnimState = "idle" | "playing";

function ScaleLogo({ size = 52 }: { size?: number }) {
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
  );
}

export default function LoginPage() {
  const [userId, setUserId] = useState("");
  const [password, setPassword] = useState("");
  const [anim, setAnim] = useState<AnimState>("idle");
  const { login, loading, error } = useAuth();
  const navigate = useNavigate();

const handleSubmit = async (e: FormEvent) => {
  e.preventDefault();
  try {
    await login(userId, password);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setAnim("playing");
        // 저울이 완전히 커진 다음에 이동
        setTimeout(() => navigate("/"), 950);
      });
    });
  } catch {}
};

  const isPlaying = anim === "playing";

  return (
    <div
      className="flex items-center justify-center min-h-screen"
      style={{ background: "var(--bg-primary)", overflow: "hidden", position: "relative" }}
    >
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl p-8 flex flex-col items-center"
        style={{
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
          position: "relative",
          zIndex: 1,
        }}
      >
        <div
          aria-hidden="true"
          style={{
            marginBottom: "12px",
            transformOrigin: "center center",
            transform: isPlaying ? "scale(30)" : "scale(1)",
            opacity: isPlaying ? 0 : 1,
            transition: isPlaying
              ? "transform 0.85s cubic-bezier(0.2,0,0.4,1), opacity 0.25s 0.65s ease"
              : "none",
          }}
        >
          <ScaleLogo size={52} />
        </div>

        <p className="text-sm font-medium mb-1" style={{ color: "var(--text-primary)" }}>
          법률 AI 워크스페이스
        </p>
        <p className="text-xs mb-7" style={{ color: "var(--text-secondary)" }}>
          사건과 문서를 한 곳에서 관리하세요
        </p>

        <div className="flex flex-col gap-1 mb-3.5 w-full">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
            아이디
          </label>
          <input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="아이디를 입력하세요"
            className="rounded-md px-3 py-2 text-sm outline-none w-full"
            style={{
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
            required
          />
        </div>

        <div className="flex flex-col gap-1 mb-2 w-full">
          <label className="text-sm" style={{ color: "var(--text-secondary)" }}>
            비밀번호
          </label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호를 입력하세요"
            className="rounded-md px-3 py-2 text-sm outline-none w-full"
            style={{
              background: "var(--bg-elevated)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
            }}
            required
          />
        </div>

        <div className="flex justify-end mb-4 w-full">
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            비밀번호를 잊으셨나요?
          </span>
        </div>

        {error && (
          <p className="text-sm mb-3 w-full" style={{ color: "var(--danger)" }}>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || isPlaying}
          className="rounded-md py-2.5 text-sm font-medium transition-opacity disabled:opacity-50 w-full"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          {loading ? "로그인 중..." : "로그인"}
        </button>

        <div className="flex items-center gap-2.5 my-5 w-full">
          <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>또는</span>
          <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
        </div>

        <p className="text-center text-sm w-full" style={{ color: "var(--text-secondary)" }}>
          아직 계정이 없으신가요?{" "}
          <Link to="/signup" style={{ color: "var(--accent-text)", fontWeight: 500 }}>
            회원가입
          </Link>
        </p>
      </form>
    </div>
  );
}