import { useEffect, useRef, useState } from "react";
import { User } from "../types";
import { AVATAR_COLORS, randomAvatarColor } from "../data/avatarColors";
import Avatar from "./Avatar";
import { PencilIcon } from "./icons";

interface RegisteredAccount {
  username: string;
  password: string;
  user: User;
}

interface AuthViewProps {
  registeredAccounts: RegisteredAccount[];
  onSignUp: (account: RegisteredAccount) => void;
  onLogIn: (user: User) => void;
}

type Mode = "login" | "signup";

export default function AuthView({ registeredAccounts, onSignUp, onLogIn }: AuthViewProps) {
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [avatarColor, setAvatarColor] = useState(randomAvatarColor());
  const [avatarImageUrl, setAvatarImageUrl] = useState<string | null>(null);
  const [showAvatarMenu, setShowAvatarMenu] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForgotNotice, setShowForgotNotice] = useState(false);
  const avatarMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!showAvatarMenu) return;
    function handleClick(e: MouseEvent) {
      if (avatarMenuRef.current && !avatarMenuRef.current.contains(e.target as Node)) {
        setShowAvatarMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showAvatarMenu]);

  const isUsernameTaken =
    mode === "signup" && username.trim() !== "" && registeredAccounts.some((a) => a.username === username.trim());

  function resetForm() {
    setName("");
    setUsername("");
    setPassword("");
    setConfirmPassword("");
    setAvatarColor(randomAvatarColor());
    setAvatarImageUrl(null);
    setShowAvatarMenu(false);
    setError(null);
    setShowForgotNotice(false);
  }

  function switchMode(next: Mode) {
    setMode(next);
    resetForm();
  }

  function handlePickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarImageUrl(URL.createObjectURL(file));
    setShowAvatarMenu(false);
  }

  function handleSignUp() {
    if (!name.trim() || !username.trim() || !password.trim() || !confirmPassword.trim()) {
      setError("이름, 아이디, 비밀번호를 모두 입력해주세요.");
      return;
    }
    if (isUsernameTaken) {
      setError("이미 사용 중인 아이디예요.");
      return;
    }
    if (password !== confirmPassword) {
      setError("비밀번호가 일치하지 않아요.");
      return;
    }

    const user: User = {
      name: name.trim(),
      username: username.trim(),
      status: "online",
      avatarColor,
      avatarImageUrl,
    };
    onSignUp({ username: username.trim(), password, user });
  }

  function handleLogIn() {
    if (!username.trim() || !password.trim()) {
      setError("아이디와 비밀번호를 입력해주세요.");
      return;
    }
    const account = registeredAccounts.find(
      (a) => a.username === username.trim() && a.password === password
    );
    if (!account) {
      setError("아이디 또는 비밀번호가 올바르지 않아요.");
      return;
    }
    onLogIn(account.user);
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-recall-bg">
      <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-lg">
        <p className="mb-1 text-lg font-semibold text-recall-text">Re:Call</p>
        <p className="mb-5 text-sm text-recall-textMuted">
          {mode === "login" ? "다시 오셨네요! 로그인해주세요." : "회원가입하고 팀과 함께 시작해보세요."}
        </p>

        {mode === "signup" && (
          <div className="mb-5 flex flex-col items-center">
            <div ref={avatarMenuRef} className="relative">
              <Avatar user={{ name, avatarColor, avatarImageUrl }} size={80} />
              <button
                onClick={() => setShowAvatarMenu((v) => !v)}
                aria-label="프로필 변경"
                className="absolute -bottom-1 -left-1 flex h-7 w-7 items-center justify-center rounded-full border border-recall-border bg-recall-bgSoft text-recall-textMuted shadow-sm hover:text-recall-text"
              >
                <PencilIcon size={13} />
              </button>

              {showAvatarMenu && (
                <div className="absolute left-1/2 top-full z-30 mt-2 w-56 -translate-x-1/2 rounded-xl border border-recall-border bg-recall-bgSoft p-3 shadow-lg">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handlePickPhoto}
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="mb-2 w-full rounded-lg border border-recall-border py-1.5 text-xs text-recall-text hover:bg-white/5"
                  >
                    내 사진 업로드
                  </button>
                  <p className="mb-1.5 text-[11px] text-recall-textMuted">또는 색상 선택</p>
                  <div className="flex flex-wrap gap-1.5">
                    {AVATAR_COLORS.map((color) => (
                      <button
                        key={color}
                        onClick={() => {
                          setAvatarColor(color);
                          setAvatarImageUrl(null);
                          setShowAvatarMenu(false);
                        }}
                        style={{ backgroundColor: color }}
                        className={`h-6 w-6 rounded-full transition ${
                          !avatarImageUrl && avatarColor === color
                            ? "ring-2 ring-recall-accent ring-offset-2 ring-offset-recall-bgSoft"
                            : "opacity-80 hover:opacity-100"
                        }`}
                        aria-label={`색상 ${color}`}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-3">
          {mode === "signup" && (
            <div>
              <label className="mb-1 block text-xs text-recall-textMuted">이름</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="이름을 입력하세요"
                className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
              />
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">아이디</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="아이디를 입력하세요"
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
            {mode === "signup" && username.trim() !== "" && (
              <p className={`mt-1 text-xs ${isUsernameTaken ? "text-recall-danger" : "text-recall-accent"}`}>
                {isUsernameTaken ? "이미 사용 중인 아이디예요." : "사용 가능한 아이디예요."}
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              onKeyDown={(e) => e.key === "Enter" && mode === "login" && handleLogIn()}
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
            {mode === "login" && (
              <button
                onClick={() => setShowForgotNotice((v) => !v)}
                className="mt-1.5 text-xs text-recall-textMuted hover:text-recall-accent"
              >
                비밀번호를 잊으셨습니까?
              </button>
            )}
            {showForgotNotice && (
              <p className="mt-1 text-xs text-recall-textMuted">
                비밀번호 재설정 기능은 아직 준비 중이에요. 곧 이메일로 재설정할 수 있게 될 거예요.
              </p>
            )}
          </div>

          {mode === "signup" && (
            <div>
              <label className="mb-1 block text-xs text-recall-textMuted">비밀번호 확인</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                onKeyDown={(e) => e.key === "Enter" && handleSignUp()}
                className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
              />
              {confirmPassword && password !== confirmPassword && (
                <p className="mt-1 text-xs text-recall-danger">비밀번호가 일치하지 않아요.</p>
              )}
            </div>
          )}
        </div>

        {error && <p className="mt-3 text-xs text-recall-danger">{error}</p>}

        <button
          onClick={mode === "login" ? handleLogIn : handleSignUp}
          className="mt-5 w-full rounded-lg bg-recall-accent py-2 text-sm font-medium text-white hover:opacity-90"
        >
          {mode === "login" ? "로그인" : "가입하기"}
        </button>

        {/* 탭 대신, 로그인 아래 구분선을 두고 회원가입/로그인으로 전환할 수 있게 함 */}
        <div className="my-4 flex items-center gap-3">
          <div className="h-px flex-1 bg-recall-border" />
          <span className="text-xs text-recall-textMuted">또는</span>
          <div className="h-px flex-1 bg-recall-border" />
        </div>

        {mode === "login" ? (
          <p className="text-center text-sm text-recall-textMuted">
            계정이 없으신가요?{" "}
            <button onClick={() => switchMode("signup")} className="text-recall-accent hover:underline">
              회원가입
            </button>
          </p>
        ) : (
          <p className="text-center text-sm text-recall-textMuted">
            이미 계정이 있으신가요?{" "}
            <button onClick={() => switchMode("login")} className="text-recall-accent hover:underline">
              로그인
            </button>
          </p>
        )}
      </div>
    </div>
  );
}