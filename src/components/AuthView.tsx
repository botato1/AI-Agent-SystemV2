import React, { useEffect, useRef, useState } from "react";
import { User } from "../types";
import { AVATAR_COLORS, randomAvatarColor } from "../data/avatarColors";
import Avatar from "./Avatar";
import { PencilIcon } from "./icons";
import { checkUserId, checkEmail, loginApi, signUpApi } from "../services/auth";

interface RegisteredAccount {
  username: string;
  email?: string;
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

  // 폼 입력 상태
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [avatarColor, setAvatarColor] = useState(randomAvatarColor());
  const [avatarImageUrl, setAvatarImageUrl] = useState<string | null>(null);
  const [showAvatarMenu, setShowAvatarMenu] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForgotNotice, setShowForgotNotice] = useState(false);

  // 이메일 분할 입력 state
  const [emailUser, setEmailUser] = useState("");
  const [emailDomain, setEmailDomain] = useState("gmail.com");
  const [customDomain, setCustomDomain] = useState("");

  const avatarMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 실시간 아이디 중복 확인 상태
  const [userIdMessage, setUserIdMessage] = useState("");
  const [isUserIdAvailable, setIsUserIdAvailable] = useState<boolean | null>(null);
  const [isUserIdChecking, setIsUserIdChecking] = useState(false);

  // 실시간 이메일 중복 확인 상태
  const [emailMessage, setEmailMessage] = useState("");
  const [isEmailAvailable, setIsEmailAvailable] = useState<boolean | null>(null);
  const [isEmailChecking, setIsEmailChecking] = useState(false);

  // 조합된 최종 이메일 주소
  const fullEmail =
    emailDomain === "custom"
      ? emailUser.trim() && customDomain.trim()
        ? `${emailUser.trim()}@${customDomain.trim()}`
        : ""
      : emailUser.trim()
      ? `${emailUser.trim()}@${emailDomain}`
      : "";

  // 아바타 메뉴 외부 클릭 감지
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

  // 1. 아이디 실시간 0.4초 디바운스 중복 체크
  useEffect(() => {
    if (mode !== "signup") return;

    const trimmedUsername = username.trim();
    if (!trimmedUsername) {
      setUserIdMessage("");
      setIsUserIdAvailable(null);
      setIsUserIdChecking(false);
      return;
    }

    if (trimmedUsername.length > 50) {
      setUserIdMessage("아이디는 50자 이내로 입력해 주세요.");
      setIsUserIdAvailable(false);
      setIsUserIdChecking(false);
      return;
    }

    setIsUserIdChecking(true);
    const timer = setTimeout(async () => {
      const result = await checkUserId(trimmedUsername);
      setIsUserIdAvailable(result.isAvailable);
      setUserIdMessage(result.message);
      setIsUserIdChecking(false);
    }, 400);

    return () => clearTimeout(timer);
  }, [username, mode]);

  // 2. 이메일 실시간 0.4초 디바운스 중복 체크
  useEffect(() => {
    if (mode !== "signup") return;

    if (!fullEmail) {
      setEmailMessage("");
      setIsEmailAvailable(null);
      setIsEmailChecking(false);
      return;
    }

    setIsEmailChecking(true);
    const timer = setTimeout(async () => {
      const result = await checkEmail(fullEmail);
      setIsEmailAvailable(result.isAvailable);
      setEmailMessage(result.message);
      setIsEmailChecking(false);
    }, 400);

    return () => clearTimeout(timer);
  }, [fullEmail, mode]);

  function resetForm() {
    setName("");
    setUsername("");
    setEmailUser("");
    setEmailDomain("gmail.com");
    setCustomDomain("");
    setPassword("");
    setConfirmPassword("");
    setAvatarColor(randomAvatarColor());
    setAvatarImageUrl(null);
    setShowAvatarMenu(false);
    setError(null);
    setShowForgotNotice(false);
    setUserIdMessage("");
    setIsUserIdAvailable(null);
    setIsUserIdChecking(false);
    setEmailMessage("");
    setIsEmailAvailable(null);
    setIsEmailChecking(false);
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

  // 백엔드 DB 회원가입 호출
  async function handleSignUp() {
    setError(null);

    if (!name.trim() || !username.trim() || !fullEmail || !password.trim() || !confirmPassword.trim()) {
      setError("모든 정보를 올바르게 입력해주세요.");
      return;
    }
    if (isUserIdAvailable === false) {
      setError("사용 가능한 아이디를 입력해주세요.");
      return;
    }
    if (isEmailAvailable === false) {
      setError("사용 가능한 이메일을 입력해주세요.");
      return;
    }
    if (password !== confirmPassword) {
      setError("비밀번호가 일치하지 않아요.");
      return;
    }

    const signUpResult = await signUpApi({
      username: username.trim(),
      email: fullEmail,
      password: password.trim(),
      displayName: name.trim(),
    });

    if (signUpResult.status === "success") {
      const newUser: User = {
        id: crypto.randomUUID(),
        name: name.trim(),
        username: username.trim(),
        status: "online",
        avatarColor,
        avatarImageUrl,
      };

      onSignUp({
        username: username.trim(),
        email: fullEmail,
        password,
        user: newUser,
      });

      // alert 경고창 없이 바로 로그인 폼으로 화면 전환
      switchMode("login");
    } else {
      setError(signUpResult.message);
    }
  }

  // 백엔드 DB 로그인 호출
  async function handleLogIn() {
    setError(null);

    if (!username.trim() || !password.trim()) {
      setError("아이디와 비밀번호를 모두 입력해주세요.");
      return;
    }

    const result = await loginApi(username, password);

    if (result.status === "success" && result.user && result.token) {
      // access_token & refresh_token 모두 로컬스토리지에 저장
      localStorage.setItem("access_token", result.token.access_token);
      if (result.token.refresh_token) {
        localStorage.setItem("refresh_token", result.token.refresh_token);
      }

      const loggedInUser: User = {
        id: result.user.id,
        name: result.user.display_name,
        username: result.user.username,
        status: "online",
        avatarColor: randomAvatarColor(),
        avatarImageUrl: null,
      };

      onLogIn(loggedInUser);
    } else {
      setError(result.message);
    }
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

          {/* 아이디 입력 */}
          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">아이디</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="아이디를 입력하세요"
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
            {mode === "signup" && (
              <div className="mt-1 min-h-[18px]">
                {isUserIdChecking ? (
                  <p className="text-xs text-recall-textMuted">중복 확인 중...</p>
                ) : userIdMessage ? (
                  <p className={`text-xs ${isUserIdAvailable ? "text-recall-accent" : "text-recall-danger"}`}>
                    {userIdMessage}
                  </p>
                ) : null}
              </div>
            )}
          </div>

          {/* 이메일 입력 (드롭다운 포함 / 회원가입 전용) */}
          {mode === "signup" && (
            <div>
              <label className="mb-1 block text-xs text-recall-textMuted">이메일</label>
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={emailUser}
                  onChange={(e) => setEmailUser(e.target.value)}
                  placeholder="이메일 주소"
                  className="w-1/2 rounded-lg border border-recall-border bg-transparent px-2.5 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
                />
                <span className="text-xs text-recall-textMuted">@</span>

                <select
                  value={emailDomain}
                  onChange={(e) => setEmailDomain(e.target.value)}
                  className="w-1/2 rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-2 text-xs text-recall-text focus:outline-none focus:border-recall-accent"
                >
                  <option value="gmail.com">gmail.com</option>
                  <option value="naver.com">naver.com</option>
                  <option value="outlook.com">outlook.com</option>
                  <option value="custom">직접 입력</option>
                </select>
              </div>

              {emailDomain === "custom" && (
                <input
                  type="text"
                  value={customDomain}
                  onChange={(e) => setCustomDomain(e.target.value)}
                  placeholder="도메인 입력 (예: company.com)"
                  className="mt-1.5 w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
                />
              )}

              <div className="mt-1 min-h-[18px]">
                {isEmailChecking ? (
                  <p className="text-xs text-recall-textMuted">중복 확인 중...</p>
                ) : emailMessage ? (
                  <p className={`text-xs ${isEmailAvailable ? "text-recall-accent" : "text-recall-danger"}`}>
                    {emailMessage}
                  </p>
                ) : null}
              </div>
            </div>
          )}

          {/* 비밀번호 입력 */}
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
                비밀번호 재설정 기능은 가입된 이메일로 발송하는 방식을 준비 중이에요.
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