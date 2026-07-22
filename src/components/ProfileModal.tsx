import React, { useRef, useState } from "react";
import { User } from "../types";
import Avatar from "./Avatar";
import { AVATAR_COLORS } from "../data/avatarColors";
import { PencilIcon } from "./icons";
import { updateProfileApi } from "../services/auth";

interface ProfileModalProps {
  user: User;
  onClose: () => void;
  onChangeAvatarColor: (color: string) => void;
  onChangeAvatarImage: (imageUrl: string) => void;
  onUpdateSuccess: (updatedUser: User) => void;
  t: any;
}

// 이미지와 동일한 얇은 꺾쇠 화살표 아이콘
function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`h-3.5 w-3.5 text-recall-textMuted transition-transform duration-200 ${
        open ? "rotate-180" : "-rotate-90"
      }`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

// ⓘ 정보 아이콘
function InfoIcon() {
  return (
    <svg className="h-3.5 w-3.5 text-recall-textMuted shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

export default function ProfileModal({
  user,
  onClose,
  onChangeAvatarColor,
  onChangeAvatarImage,
  onUpdateSuccess,
  t,
}: ProfileModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [displayName, setDisplayName] = useState(user.name);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [showAvatarMenu, setShowAvatarMenu] = useState(false);
  const [showPasswordSection, setShowPasswordSection] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handlePickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    onChangeAvatarImage(URL.createObjectURL(file));
    setShowAvatarMenu(false);
  }

  async function handleSaveProfile() {
    setError(null);
    setSuccessMessage(null);

    if (!displayName.trim()) {
      setError("이름을 입력해 주세요.");
      return;
    }

    if (showPasswordSection) {
      if (!currentPassword.trim()) {
        setError("현재 비밀번호를 입력해 주세요.");
        return;
      }
      if (!newPassword.trim()) {
        setError("새 비밀번호를 입력해 주세요.");
        return;
      }
      if (newPassword !== confirmPassword) {
        setError("새 비밀번호가 일치하지 않습니다.");
        return;
      }
      if (currentPassword === newPassword) {
        setError("새 비밀번호는 현재 비밀번호와 다르게 설정해 주세요.");
        return;
      }
    }

    setIsSubmitting(true);

    const result = await updateProfileApi({
      displayName: displayName.trim() !== user.name ? displayName.trim() : undefined,
      currentPassword: showPasswordSection && currentPassword ? currentPassword : undefined,
      newPassword: showPasswordSection && newPassword ? newPassword : undefined,
    });

    setIsSubmitting(false);

    if (result.status === "success") {
      setSuccessMessage("프로필이 성공적으로 업데이트되었습니다.");
      if (result.user) {
        onUpdateSuccess({
          ...user,
          name: result.user.display_name,
        });
      }
      setTimeout(() => {
        onClose();
      }, 800);
    } else {
      setError(result.message);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-xl text-recall-text">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold">프로필 설정</h2>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text">
            ✕
          </button>
        </div>

        {/* 아바타 & 연필 아이콘 */}
        <div className="flex flex-col items-center mb-6">
          <div className="relative">
            <Avatar user={user} size={80} />
            <button
              onClick={() => setShowAvatarMenu((v) => !v)}
              aria-label="프로필 변경"
              className="absolute -bottom-1 -right-1 flex h-7 w-7 items-center justify-center rounded-full border border-recall-border bg-recall-bgSoft text-recall-textMuted shadow-sm hover:text-recall-text transition"
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
                        onChangeAvatarColor(color);
                        setShowAvatarMenu(false);
                      }}
                      style={{ backgroundColor: color }}
                      className={`h-6 w-6 rounded-full transition ${
                        !user.avatarImageUrl && user.avatarColor === color
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

        {/* 입력 폼 영역 */}
        <div className="flex flex-col gap-3.5">
          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">아이디</label>
            <input
              type="text"
              value={user.username}
              disabled
              className="w-full rounded-lg border border-recall-border bg-white/5 px-3 py-2 text-sm text-recall-textMuted cursor-not-allowed"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">이름</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="이름 입력"
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:border-recall-accent"
            />
          </div>

          {/* 비밀번호 변경 영역 (이미지 디자인 적용) */}
          <div className="mt-1 border-t border-recall-border/50 pt-3">
            <button
              type="button"
              onClick={() => {
                setShowPasswordSection((v) => !v);
                setError(null);
                setSuccessMessage(null);
              }}
              className="flex items-center gap-1.5 text-xs text-recall-text font-medium hover:opacity-80 transition"
            >
              <ChevronIcon open={showPasswordSection} />
              <span>비밀번호 변경</span>
            </button>

            {showPasswordSection && (
              <div className="mt-3.5 flex flex-col gap-3">
                <div>
                  <label className="mb-1 block text-xs text-recall-textMuted">현재 비밀번호</label>
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="현재 비밀번호 입력"
                    className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:border-recall-accent"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-xs text-recall-textMuted">새 비밀번호</label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="새 비밀번호 입력"
                    className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:border-recall-accent"
                  />
                  <div className="mt-1 flex items-center gap-1 text-[11px] text-recall-textMuted">
                    <InfoIcon />
                    <span>8자 이상, 영문·숫자 포함</span>
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-xs text-recall-textMuted">새 비밀번호 확인</label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="새 비밀번호 다시 입력"
                    className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:border-recall-accent"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 에러 및 성공 메시지 */}
        <div className="mt-2 min-h-[18px]">
          {error && <p className="text-xs text-recall-danger leading-relaxed">{error}</p>}
          {successMessage && <p className="text-xs text-emerald-400 font-medium leading-relaxed">{successMessage}</p>}
        </div>

        {/* 하단 취소 / 저장 버튼 */}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-recall-border px-4 py-2 text-xs text-recall-textMuted hover:bg-white/5"
          >
            취소
          </button>
          <button
            onClick={handleSaveProfile}
            disabled={isSubmitting}
            className="rounded-lg bg-recall-accent px-4 py-2 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 transition"
          >
            {isSubmitting ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}