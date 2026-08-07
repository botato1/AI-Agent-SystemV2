import React, { useRef, useState, useEffect } from "react";
import { User } from "../types";
import Avatar from "./Avatar";
import { AVATAR_COLORS } from "../data/avatarColors";
import { PencilIcon } from "./icons";
import { updateProfileApi } from "../services/auth";
import AvatarCropModal from "./AvatarCropModal";
import { validatePassword } from "../data/passwordPolicy";

// 목소리 프로필 API 및 모달 연동
import {
  getVoiceProfileStatusApi,
  deleteVoiceProfileApi,
  renameVoiceProfileApi,
  VoiceProfileStatus,
} from "../services/voice";
import { VoiceRegisterModal } from "./VoiceRegisterModal"; 

interface ProfileModalProps {
  user: User;
  onClose: () => void;
  onChangeAvatarColor: (color: string) => void;
  onChangeAvatarImage: (file: File) => void;
  onUpdateSuccess: (updatedUser: User) => void;
  t: any;
}

// 얇은 꺾쇠 화살표 아이콘
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

  // 목소리 등록 섹션 관련 State
  const [showVoiceSection, setShowVoiceSection] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceProfileStatus | null>(null);
  const [isVoiceLoading, setIsVoiceLoading] = useState(false);
  const [isVoiceRegisterModalOpen, setIsVoiceRegisterModalOpen] = useState(false);

  // STT 인식 이름 수정용 State
  const [isEditingVoiceName, setIsEditingVoiceName] = useState(false);
  const [editingVoiceName, setEditingVoiceName] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [cropFile, setCropFile] = useState<File | null>(null);

  // 컴포넌트 마운트 시 목소리 등록 상태 조회
  useEffect(() => {
    fetchVoiceStatus();
  }, []);

  const fetchVoiceStatus = async () => {
    setIsVoiceLoading(true);
    const res = await getVoiceProfileStatusApi();
    setIsVoiceLoading(false);
    if (res.status === "success" && res.data) {
      setVoiceStatus(res.data);
      if (res.data.speaker_name) {
        setEditingVoiceName(res.data.speaker_name);
      }
    }
  };

  // 목소리 프로필 삭제
  const handleDeleteVoice = async () => {
    if (!window.confirm(t.profile_voice_delete_confirm)) return;
    setError(null);
    setSuccessMessage(null);

    const res = await deleteVoiceProfileApi();
    if (res.status === "success") {
      setSuccessMessage(t.profile_voice_deleted_msg);
      fetchVoiceStatus();
    } else {
      setError(res.message);
    }
  };

  // STT 이름 수정
  const handleRenameVoice = async () => {
    if (!editingVoiceName.trim()) {
      setError(t.profile_voice_name_invalid);
      return;
    }
    setError(null);
    setSuccessMessage(null);

    const res = await renameVoiceProfileApi(editingVoiceName.trim());
    if (res.status === "success") {
      setSuccessMessage(t.profile_voice_name_updated_msg);
      setIsEditingVoiceName(false);
      fetchVoiceStatus();
    } else {
      setError(res.message);
    }
  };

  function handlePickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setCropFile(file);
    setShowAvatarMenu(false);
    e.target.value = "";
  }

  async function handleSaveProfile() {
    setError(null);
    setSuccessMessage(null);

    if (!displayName.trim()) {
      setError(t.profile_name_required);
      return;
    }

    if (showPasswordSection) {
      if (!currentPassword.trim()) {
        setError(t.settings_account_delete_password_required);
        return;
      }
      if (!newPassword.trim()) {
        setError(t.profile_new_password_required);
        return;
      }
      if (newPassword !== confirmPassword) {
        setError(t.profile_password_mismatch);
        return;
      }
      if (currentPassword === newPassword) {
        setError(t.profile_password_same_as_current);
        return;
      }
      const policyError = validatePassword(newPassword);
      if (policyError) {
        setError(policyError);
        return;
      }
    }

    const nameChanged = displayName.trim() !== user.name;
    const passwordChangeRequested = showPasswordSection && !!currentPassword && !!newPassword;

    if (!nameChanged && !passwordChangeRequested) {
      onClose();
      return;
    }

    setIsSubmitting(true);

    const result = await updateProfileApi({
      displayName: displayName.trim() !== user.name ? displayName.trim() : undefined,
      currentPassword: showPasswordSection && currentPassword ? currentPassword : undefined,
      newPassword: showPasswordSection && newPassword ? newPassword : undefined,
    });

    setIsSubmitting(false);

    if (result.status === "success") {
      setSuccessMessage(t.profile_update_success);
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
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-sm max-h-[90vh] overflow-y-auto rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-xl text-recall-text custom-scrollbar">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold">{t.profile_modal_title}</h2>
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
              aria-label={t.profile_change_avatar_aria}
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
                  className="mb-2 w-full rounded-lg border border-recall-border py-1.5 text-sm text-recall-text hover:bg-white/5"
                >
                  {t.profile_upload_photo}
                </button>
                <p className="mb-1.5 text-xs text-recall-textMuted">{t.profile_or_color}</p>
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
                      aria-label={t.profile_color_aria(color)}
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
            <label className="mb-1 block text-sm text-recall-textMuted">{t.profile_id}</label>
            <input
              type="text"
              value={user.username}
              disabled
              className="w-full rounded-lg border border-recall-border bg-white/5 px-3 py-2 text-base text-recall-textMuted cursor-not-allowed"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">{t.profile_name}</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={t.profile_name_placeholder}
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base focus:outline-none focus:border-recall-accent"
            />
          </div>

          {/* 목소리 등록하기 영역 */}
          <div className="mt-1 border-t border-recall-border/50 pt-3">
            <button
              type="button"
              onClick={() => {
                setShowVoiceSection((v) => !v);
                setError(null);
                setSuccessMessage(null);
              }}
              className="flex items-center justify-between w-full text-sm text-recall-text font-medium hover:opacity-80 transition"
            >
              <div className="flex items-center gap-1.5">
                <ChevronIcon open={showVoiceSection} />
                <span>{t.profile_voice_section_title}</span>
              </div>
              <span className="text-xs font-normal">
                {voiceStatus?.registered ? (
                  <span className="text-emerald-400 font-medium">{t.profile_voice_registered}</span>
                ) : (
                  <span className="text-recall-textMuted">{t.profile_voice_unregistered}</span>
                )}
              </span>
            </button>

            {showVoiceSection && (
              <div className="mt-3.5 flex flex-col gap-3 rounded-xl border border-recall-border/60 bg-white/5 p-3.5 text-xs">
                {isVoiceLoading ? (
                  <p className="text-recall-textMuted">{t.profile_voice_status_loading}</p>
                ) : voiceStatus?.registered ? (
                  <div className="flex flex-col gap-2.5">
                    <div className="flex items-center justify-between bg-white/5 p-2 rounded-lg border border-recall-border/40">
                      <span className="text-recall-textMuted">{t.profile_voice_recognized_name}</span>
                      {isEditingVoiceName ? (
                        <div className="flex items-center gap-1">
                          <input
                            type="text"
                            value={editingVoiceName}
                            onChange={(e) => setEditingVoiceName(e.target.value)}
                            className="w-20 rounded border border-recall-border bg-transparent px-1.5 py-0.5 text-xs focus:outline-none focus:border-recall-accent"
                          />
                          <button
                            type="button"
                            onClick={handleRenameVoice}
                            className="rounded bg-recall-accent px-2 py-0.5 text-xs text-white"
                          >
                            {t.task_save}
                          </button>
                          <button
                            type="button"
                            onClick={() => setIsEditingVoiceName(false)}
                            className="text-recall-textMuted hover:text-recall-text px-1"
                          >
                            {t.task_cancel}
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-recall-text">{voiceStatus.speaker_name}</span>
                          <button
                            type="button"
                            onClick={() => setIsEditingVoiceName(true)}
                            className="text-recall-textMuted hover:text-recall-text underline text-[11px]"
                          >
                            {t.meeting_export_edit}
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-between mt-1">
                      <button
                        type="button"
                        onClick={() => setIsVoiceRegisterModalOpen(true)}
                        className="rounded-lg border border-recall-border px-3 py-1.5 text-recall-text hover:bg-white/5 transition"
                      >
                        {t.profile_voice_reregister}
                      </button>
                      <button
                        type="button"
                        onClick={handleDeleteVoice}
                        className="text-red-400 hover:text-red-300 underline text-xs"
                      >
                        {t.profile_voice_delete}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2.5">
                    <button
                      type="button"
                      onClick={() => setIsVoiceRegisterModalOpen(true)}
                      className="mt-1 w-full rounded-lg bg-recall-accent py-2 font-medium text-white hover:opacity-90 transition text-sm shadow-sm"
                    >
                      {t.profile_voice_section_title}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 비밀번호 변경 영역 */}
          <div className="mt-1 border-t border-recall-border/50 pt-3">
            <button
              type="button"
              onClick={() => {
                setShowPasswordSection((v) => !v);
                setError(null);
                setSuccessMessage(null);
              }}
              className="flex items-center gap-1.5 text-sm text-recall-text font-medium hover:opacity-80 transition"
            >
              <ChevronIcon open={showPasswordSection} />
              <span>{t.profile_change_pwd}</span>
            </button>

            {showPasswordSection && (
              <div className="mt-3.5 flex flex-col gap-3">
                <div>
                  <label className="mb-1 block text-sm text-recall-textMuted">{t.profile_password_current}</label>
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder={t.profile_password_current_placeholder}
                    className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base focus:outline-none focus:border-recall-accent"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm text-recall-textMuted">{t.profile_password_new}</label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder={t.profile_password_new_placeholder}
                    className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base focus:outline-none focus:border-recall-accent"
                  />
                  <div className="mt-1 flex items-center gap-1 text-xs text-recall-textMuted">
                    <InfoIcon />
                    <span>{t.profile_password_policy_hint}</span>
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-sm text-recall-textMuted">{t.profile_password_confirm}</label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder={t.profile_password_confirm_placeholder}
                    className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base focus:outline-none focus:border-recall-accent"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 에러 및 성공 메시지 */}
        <div className="mt-2 min-h-[18px]">
          {error && <p className="text-sm text-recall-danger leading-relaxed">{error}</p>}
          {successMessage && <p className="text-sm text-emerald-400 font-medium leading-relaxed">{successMessage}</p>}
        </div>

        {/* 하단 취소 / 저장 버튼 */}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-recall-border px-4 py-2 text-sm text-recall-textMuted hover:bg-white/5"
          >
            {t.task_cancel}
          </button>
          <button
            onClick={handleSaveProfile}
            disabled={isSubmitting}
            className="rounded-lg bg-recall-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 transition"
          >
            {isSubmitting ? t.meeting_export_saving : t.task_save}
          </button>
        </div>
      </div>

      {cropFile && (
        <AvatarCropModal
          file={cropFile}
          onCancel={() => setCropFile(null)}
          onConfirm={(croppedFile) => {
            onChangeAvatarImage(croppedFile);
            setCropFile(null);
          }}
        />
      )}

      {/* 목소리 등록 모달 */}
      <VoiceRegisterModal
        isOpen={isVoiceRegisterModalOpen}
        onClose={() => setIsVoiceRegisterModalOpen(false)}
        onSuccess={() => {
          setSuccessMessage(t.profile_voice_registered_msg);
          fetchVoiceStatus();
        }}
      />
    </div>
  );
}