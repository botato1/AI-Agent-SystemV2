import React, { useEffect, useRef, useState } from "react";
import { User } from "../types";
import { AVATAR_COLORS, randomAvatarColor, hashAvatarColor, loadAvatarColor, saveAvatarColor } from "../data/avatarColors";
import Avatar from "./Avatar";
import { PencilIcon } from "./icons";
import {
  checkEmail,
  checkUserId,
  loginApi,
  requestPasswordResetApi,
  resolveAvatarUrl,
  signUpApi,
} from "../services/auth";

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
  const [isSubmitting, setIsSubmitting] = useState(false);

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

  // 비밀번호 재설정 모달 상태
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetEmail, setResetEmail] = useState("");
  const [resetMessage, setResetMessage] = useState<string | null>(null);
  const [isResetError, setIsResetError] = useState(false);
  const [isResetSubmitting, setIsResetSubmitting] = useState(false);

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

    setIsSubmitting(true);

    const signUpResult = await signUpApi({
      username: username.trim(),
      email: fullEmail,
      password: password.trim(),
      displayName: name.trim(),
    });

    setIsSubmitting(false);

    if (signUpResult.status === "success") {
      saveAvatarColor(username.trim(), avatarColor);

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

    setIsSubmitting(true);

    const result = await loginApi(username, password);

    setIsSubmitting(false);

    if (result.status === "success" && result.user && result.token) {
      localStorage.setItem("access_token", result.token.access_token);
      if (result.token.refresh_token) {
        localStorage.setItem("refresh_token", result.token.refresh_token);
      }

      const fixedAvatarColor =
        loadAvatarColor(result.user.username) || hashAvatarColor(result.user.username);
      saveAvatarColor(result.user.username, fixedAvatarColor);

      const loggedInUser: User = {
        id: result.user.id,
        name: result.user.display_name,
        username: result.user.username,
        status: "online",
        avatarColor: fixedAvatarColor,
        avatarImageUrl: resolveAvatarUrl(result.user.profile_image_url),
      };

      onLogIn(loggedInUser);
    } else {
      setError(result.message);
    }
  }

  // 비밀번호 재설정 요청 제출 (POST /api/auth/password-reset/request)
  const handlePasswordResetSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setResetMessage(null);

    if (!resetEmail.trim()) {
      setIsResetError(true);
      setResetMessage("이메일 주소를 입력해 주세요.");
      return;
    }

    setIsResetSubmitting(true);

    const res = await requestPasswordResetApi(resetEmail);

    setIsResetSubmitting(false);

    if (res.status === "success") {
      setIsResetError(false);
      setResetMessage(res.message);
    } else {
      setIsResetError(true);
      setResetMessage(res.message);
    }
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-recall-bg p-4 text-recall-text">
      <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-lg">
        <p className="mb-1 text-xl font-semibold text-recall-text">Re:Call</p>
        <p className="mb-5 text-base text-recall-textMuted">
          {mode === "login" ? "다시 오셨네요! 로그인해주세요." : "회원가입하고 팀과 함께 시작해보세요."}
        </p>

        {/* 회원가입 모드일 때만 아바타 노출 */}
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
                    className="mb-2 w-full rounded-lg border border-recall-border py-1.5 text-sm text-recall-text hover:bg-white/5"
                  >
                    내 사진 업로드
                  </button>
                  <p className="mb-1.5 text-xs text-recall-textMuted">또는 색상 선택</p>
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
          {/* 이름 입력 (회원가입) */}
          {mode === "signup" && (
            <div>
              <label className="mb-1 block text-sm text-recall-textMuted">이름</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="이름을 입력하세요"
                className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
              />
            </div>
          )}

          {/* 아이디 입력 */}
          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">아이디</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="아이디를 입력하세요"
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
            {mode === "signup" && (
              <div className="mt-1 min-h-[18px]">
                {isUserIdChecking ? (
                  <p className="text-sm text-recall-textMuted">중복 확인 중...</p>
                ) : userIdMessage ? (
                  <p className={`text-sm ${isUserIdAvailable ? "text-emerald-400" : "text-recall-danger"}`}>
                    {userIdMessage}
                  </p>
                ) : null}
              </div>
            )}
          </div>

          {/* 이메일 입력 (회원가입 분할 드롭다운) */}
          {mode === "signup" && (
            <div>
              <label className="mb-1 block text-sm text-recall-textMuted">이메일</label>
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={emailUser}
                  onChange={(e) => setEmailUser(e.target.value)}
                  placeholder="이메일 주소"
                  className="w-1/2 rounded-lg border border-recall-border bg-transparent px-2.5 py-2 text-base text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
                />
                <span className="text-sm text-recall-textMuted">@</span>
                <select
                  value={emailDomain}
                  onChange={(e) => setEmailDomain(e.target.value)}
                  className="w-1/2 rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-2 text-sm text-recall-text focus:outline-none focus:border-recall-accent"
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
                  className="mt-1.5 w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
                />
              )}

              <div className="mt-1 min-h-[18px]">
                {isEmailChecking ? (
                  <p className="text-sm text-recall-textMuted">중복 확인 중...</p>
                ) : emailMessage ? (
                  <p className={`text-sm ${isEmailAvailable ? "text-emerald-400" : "text-recall-danger"}`}>
                    {emailMessage}
                  </p>
                ) : null}
              </div>
            </div>
          )}

          {/* 비밀번호 입력 */}
          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              onKeyDown={(e) => e.key === "Enter" && mode === "login" && handleLogIn()}
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
            {mode === "login" && (
              <button
                type="button"
                onClick={() => {
                  setShowResetModal(true);
                  setResetMessage(null);
                  setResetEmail("");
                }}
                className="mt-1.5 text-sm text-recall-textMuted hover:text-recall-accent hover:underline transition"
              >
                비밀번호를 잊으셨습니까?
              </button>
            )}
          </div>

          {/* 비밀번호 확인 (회원가입) */}
          {mode === "signup" && (
            <div>
              <label className="mb-1 block text-sm text-recall-textMuted">비밀번호 확인</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                onKeyDown={(e) => e.key === "Enter" && handleSignUp()}
                className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
              />
              {confirmPassword && password !== confirmPassword && (
                <p className="mt-1 text-sm text-recall-danger">비밀번호가 일치하지 않아요.</p>
              )}
            </div>
          )}
        </div>

        {error && <p className="mt-3 text-sm text-recall-danger">{error}</p>}

        <button
          onClick={mode === "login" ? handleLogIn : handleSignUp}
          disabled={isSubmitting}
          className="mt-5 w-full rounded-lg bg-recall-accent py-2 text-base font-medium text-white hover:opacity-90 disabled:opacity-50 transition"
        >
          {isSubmitting
            ? "처리 중..."
            : mode === "login"
            ? "로그인"
            : "가입하기"}
        </button>

        <div className="my-4 flex items-center gap-3">
          <div className="h-px flex-1 bg-recall-border" />
          <span className="text-sm text-recall-textMuted">또는</span>
          <div className="h-px flex-1 bg-recall-border" />
        </div>

        {/* 하단 모드 전환 영역 */}
        {mode === "login" ? (
          <p className="text-center text-base text-recall-textMuted">
            계정이 없으신가요?{" "}
            <button
              onClick={() => switchMode("signup")}
              className="text-recall-accent hover:underline font-medium"
            >
              회원가입
            </button>
          </p>
        ) : (
          <p className="text-center text-base text-recall-textMuted">
            이미 계정이 있으신가요?{" "}
            <button
              onClick={() => switchMode("login")}
              className="text-recall-accent hover:underline font-medium"
            >
              로그인
            </button>
          </p>
        )}
      </div>

      {/* 비밀번호 재설정 모달 */}
      {showResetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-xl text-recall-text">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold">비밀번호 재설정</h2>
              <button
                onClick={() => setShowResetModal(false)}
                className="text-recall-textMuted hover:text-recall-text"
              >
                ✕
              </button>
            </div>

            <p className="mb-4 text-sm text-recall-textMuted leading-relaxed">
              가입하신 이메일 주소를 입력하시면 비밀번호 재설정 링크를 보내드립니다.
            </p>

            <form onSubmit={handlePasswordResetSubmit} className="flex flex-col gap-3">
              <div>
                <label className="mb-1 block text-sm text-recall-textMuted">
                  이메일 주소
                </label>
                <input
                  type="email"
                  value={resetEmail}
                  onChange={(e) => setResetEmail(e.target.value)}
                  placeholder="example@email.com"
                  className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base focus:border-recall-accent focus:outline-none"
                />
              </div>

              {resetMessage && (
                <p
                  className={`text-sm leading-relaxed ${
                    isResetError ? "text-recall-danger" : "text-emerald-400 font-medium"
                  }`}
                >
                  {/* (계정이 존재하는 경우) 문구를 지워 서 출력 */}
                  {resetMessage.replace(/\s*\(계정이 존재하는 경우\)/g, "")}
                </p>
              )}

              <div className="mt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowResetModal(false)}
                  className="rounded-lg border border-recall-border px-3.5 py-1.5 text-sm text-recall-textMuted hover:bg-white/5"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={isResetSubmitting}
                  className="rounded-lg bg-recall-accent px-3.5 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 transition"
                >
                  {isResetSubmitting ? "전송 중..." : "재설정 링크 발송"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}