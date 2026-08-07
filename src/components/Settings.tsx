import React, { useEffect, useState } from "react";
import { Language } from "../data/translations";
import { ChevronRightIcon, MoonIcon, SunIcon } from "./icons";
import { Theme } from "../hooks/useTheme";
import { Workspace } from "../types";
import { getWorkspaceMembersApi, WorkspaceMemberInfo } from "../services/workspace";
import { resolveAvatarUrl, DeleteAccountResponse } from "../services/auth";
import { hashAvatarColor } from "../data/avatarColors";
import Avatar from "./Avatar";
import {
  getNotificationPreferencesApi,
  updateNotificationPreferencesApi,
  NotificationPreferences,
} from "../services/notification";

interface SettingsProps {
  onClose: () => void;
  currentWorkspace?: Workspace | null;
  theme: Theme;
  onToggleTheme: () => void;
  lang: Language;
  onChangeLang: (lang: Language) => void;
  t: any;
  onLogout: () => void | Promise<void>;
  onDeleteAccount?: (password: string) => Promise<DeleteAccountResponse>;
}

export default function Settings({
  onClose,
  currentWorkspace,
  theme,
  onToggleTheme,
  lang,
  onChangeLang,
  t,
  onLogout,
  onDeleteAccount,
}: SettingsProps) {
  const [members, setMembers] = useState<WorkspaceMemberInfo[] | null>(null);
  const [isMembersOpen, setIsMembersOpen] = useState(false);
  const [notifPrefs, setNotifPrefs] = useState<NotificationPreferences | null>(null);
  const [savingNotifKey, setSavingNotifKey] = useState<keyof NotificationPreferences | null>(null);
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  function closeDeleteConfirm() {
    setIsDeleteConfirmOpen(false);
    setDeletePassword("");
    setDeleteError(null);
  }

  async function handleConfirmDelete() {
    if (!onDeleteAccount) {
      closeDeleteConfirm();
      onClose();
      onLogout();
      return;
    }
    if (!deletePassword) {
      setDeleteError(t.settings_account_delete_password_required);
      return;
    }

    setIsDeleting(true);
    setDeleteError(null);
    const res = await onDeleteAccount(deletePassword);
    setIsDeleting(false);

    if (res.status === "success") {
      closeDeleteConfirm();
      onClose();
    } else {
      setDeleteError(res.message);
    }
  }

  // 워크스페이스 멤버 목록 실시간 조회
  useEffect(() => {
    async function fetchMembers() {
      if (!currentWorkspace?.id) return;
      const res = await getWorkspaceMembersApi(currentWorkspace.id);
      if (res.status === "success" && res.members) {
        setMembers(res.members);
      }
    }

    fetchMembers();
  }, [currentWorkspace?.id]);

  // 알림 설정 조회 (한 번도 바꾼 적 없으면 서버가 전부 true로 내려줌)
  useEffect(() => {
    async function fetchNotifPrefs() {
      if (!currentWorkspace?.id) return;
      const res = await getNotificationPreferencesApi(currentWorkspace.id);
      if (res.status === "success" && res.preferences) {
        setNotifPrefs(res.preferences);
      }
    }

    fetchNotifPrefs();
  }, [currentWorkspace?.id]);

  async function handleToggleNotif(key: keyof NotificationPreferences) {
    if (!currentWorkspace?.id || !notifPrefs || savingNotifKey) return;
    const nextValue = !notifPrefs[key];
    setNotifPrefs({ ...notifPrefs, [key]: nextValue });
    setSavingNotifKey(key);

    const res = await updateNotificationPreferencesApi(currentWorkspace.id, { [key]: nextValue });
    setSavingNotifKey(null);
    if (res.status === "success" && res.preferences) {
      setNotifPrefs(res.preferences);
    } else {
      setNotifPrefs((prev) => (prev ? { ...prev, [key]: !nextValue } : prev));
      alert(res.message);
    }
  }

  // 워크스페이스 정보
  const workspaceSectionItems = [
    {
      label: t.settings_workspace_name || "워크스페이스 이름",
      value: currentWorkspace?.name || t.settings_no_workspace_selected,
    },
  ];

  // 알림 설정
  const notificationSectionItems: { key: keyof NotificationPreferences; label: string }[] = [
    { key: "new_message", label: t.settings_notif_new || "새 메시지 알림" },
    { key: "meeting_summary", label: t.settings_notif_start || "회의 시작 알림" },
    { key: "contradiction", label: t.settings_notif_contra || "회의 도움 알림" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="flex h-[520px] w-[500px] flex-col rounded-2xl border border-recall-border bg-recall-bg text-recall-text shadow-2xl">
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-recall-border px-6 py-4">
          <p className="text-lg font-bold">{t.settings_title || "설정"}</p>
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-recall-textMuted hover:text-recall-text transition"
          >
            {t.btn_close || "닫기"}
          </button>
        </div>

        {/* 본문 스크롤 영역 */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* 1. 워크스페이스 구역 */}
          <div>
            <p className="mb-2 text-sm font-semibold text-recall-textMuted">
              {t.workspace || "워크스페이스"}
            </p>
            <div className="overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
              {workspaceSectionItems.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between border-b border-recall-border px-4 py-3 text-base"
                >
                  <span className="text-recall-text font-medium">{item.label}</span>
                  <span className="text-recall-textMuted font-medium">{item.value}</span>
                </div>
              ))}

              {/* 팀원 관리 - 눌러서 펼치면 멤버별 프로필 사진/이름/권한을 보여줌 */}
              <button
                type="button"
                onClick={() => setIsMembersOpen((prev) => !prev)}
                className="flex w-full items-center justify-between px-4 py-3 text-base hover:bg-white/5 transition"
              >
                <span className="text-recall-text font-medium">{t.settings_member_count}</span>
                <span className="flex items-center gap-1.5 text-recall-textMuted font-medium">
                  {members !== null ? `${members.length}${lang === "ko" ? "명" : ""}` : t.common_loading}
                  <ChevronRightIcon
                    size={14}
                    className={`transition-transform ${isMembersOpen ? "rotate-90" : ""}`}
                  />
                </span>
              </button>

              {isMembersOpen && (
                <div className="border-t border-recall-border bg-black/10 px-4 py-2">
                  {members === null ? (
                    <p className="py-2 text-sm text-recall-textMuted">{t.common_loading}</p>
                  ) : (
                    members.map((m) => (
                      <div key={m.user_id} className="flex items-center gap-2.5 py-2">
                        <Avatar
                          user={{
                            name: m.display_name || m.username,
                            avatarColor: hashAvatarColor(m.user_id),
                            avatarImageUrl: resolveAvatarUrl(m.profile_image_url),
                          }}
                          size={28}
                        />
                        <span className="flex-1 text-sm font-medium text-recall-text">
                          {m.display_name || m.username}
                        </span>
                        <span className="text-xs text-recall-textMuted">
                          {m.role === "owner" ? t.settings_member_role_owner : t.settings_member_role_member}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 2. 알림 구역 */}
          <div>
            <p className="mb-2 text-sm font-semibold text-recall-textMuted">
              {t.settings_notif || "알림"}
            </p>
            <div className="overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
              {notifPrefs === null ? (
                <p className="px-4 py-3 text-sm text-recall-textMuted">{t.common_loading}</p>
              ) : (
                notificationSectionItems.map((item, idx) => (
                  <button
                    key={item.key}
                    type="button"
                    disabled={savingNotifKey === item.key}
                    onClick={() => handleToggleNotif(item.key)}
                    className={`flex w-full items-center justify-between px-4 py-3 text-base hover:bg-white/5 transition disabled:opacity-50 ${
                      idx < notificationSectionItems.length - 1 ? "border-b border-recall-border" : ""
                    }`}
                  >
                    <span className="text-recall-text font-medium">{item.label}</span>
                    <div
                      className={`relative h-5 w-9 flex-shrink-0 rounded-full transition-colors ${
                        notifPrefs[item.key] ? "bg-recall-accent" : "bg-recall-border"
                      }`}
                    >
                      <div
                        className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                          notifPrefs[item.key] ? "translate-x-4" : "translate-x-0"
                        }`}
                      />
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* 3. 화면 구역 */}
          <div>
            <p className="mb-2 text-sm font-semibold text-recall-textMuted">
              {t.settings_display || "화면"}
            </p>
            <div className="overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
              {/* 다크/라이트 모드 스위치 */}
              <button
                type="button"
                onClick={onToggleTheme}
                className="flex w-full items-center justify-between border-b border-recall-border px-4 py-3 text-base hover:bg-white/5 transition"
              >
                <span className="flex items-center gap-2 text-recall-text font-medium">
                  {theme === "dark" ? <MoonIcon size={14} /> : <SunIcon size={14} />}
                  {theme === "dark" ? t.settings_theme_dark || "다크 모드" : t.settings_theme_light || "라이트 모드"}
                </span>
                <div
                  className={`relative h-5 w-9 flex-shrink-0 rounded-full transition-colors ${
                    theme === "dark" ? "bg-recall-accent" : "bg-recall-border"
                  }`}
                >
                  <div
                    className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                      theme === "dark" ? "translate-x-4" : "translate-x-0"
                    }`}
                  />
                </div>
              </button>

              {/* 언어 설정 */}
              <button
                type="button"
                onClick={() => onChangeLang(lang === "ko" ? "en" : "ko")}
                className="flex w-full items-center justify-between px-4 py-3 text-base hover:bg-white/5 transition"
              >
                <span className="text-recall-text font-medium">{t.settings_lang || "언어"}</span>
                <span className="font-semibold text-recall-accent">
                  {lang === "ko" ? "한국어" : "English"}
                </span>
              </button>
            </div>
          </div>

          {/* 4. 계정 관리 구역 */}
          <div>
            <p className="mb-2 text-sm font-semibold text-recall-textMuted">
              {t.settings_account_title}
            </p>
            <div className="overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
              <button
                type="button"
                onClick={() => setIsDeleteConfirmOpen(true)}
                className="flex w-full items-center justify-between px-4 py-3 text-base font-medium text-recall-danger hover:bg-recall-danger/10 transition"
              >
                <span>{t.settings_account_delete_short}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {isDeleteConfirmOpen && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-5 text-recall-text shadow-2xl">
            <div className="mb-3 flex items-center gap-3 text-recall-danger">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-recall-danger/10 text-xl">
                🗑️
              </div>
              <h4 className="text-lg font-bold text-recall-text">{t.settings_account_delete_short}</h4>
            </div>

            <p className="mb-4 text-sm leading-relaxed text-recall-textMuted">
              {t.settings_account_delete_warning_prefix}{" "}
              <span className="font-bold text-recall-text">{t.settings_account_delete_warning_bold}</span>
              {t.settings_account_delete_warning_suffix}
            </p>

            {onDeleteAccount && (
              <div className="mb-4">
                <label className="mb-1 block text-sm font-semibold text-recall-textMuted">
                  {t.settings_account_delete_password_label}
                </label>
                <input
                  type="password"
                  autoFocus
                  value={deletePassword}
                  onChange={(e) => {
                    setDeletePassword(e.target.value);
                    setDeleteError(null);
                  }}
                  onKeyDown={(e) => e.key === "Enter" && handleConfirmDelete()}
                  placeholder={t.settings_account_delete_password_placeholder}
                  className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-sm text-recall-text outline-none focus:border-recall-danger"
                />
                {deleteError && <p className="mt-1.5 text-sm text-recall-danger">{deleteError}</p>}
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={closeDeleteConfirm}
                disabled={isDeleting}
                className="rounded-lg border border-recall-border px-3.5 py-2 text-sm text-recall-textMuted hover:bg-white/5 transition disabled:opacity-50"
              >
                {t.task_cancel}
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="rounded-lg bg-recall-danger px-3.5 py-2 text-sm font-semibold text-white hover:opacity-90 transition shadow-md shadow-recall-danger/20 disabled:opacity-50"
              >
                {isDeleting ? t.settings_account_deleting : t.settings_account_delete_confirm_btn}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}