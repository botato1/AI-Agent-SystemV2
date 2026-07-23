import React, { useEffect, useState } from "react";
import { Language } from "../data/translations";
import { MoonIcon, SunIcon } from "./icons";
import { Theme } from "../hooks/useTheme";
import { Workspace } from "../types";
import { getWorkspaceMembersApi } from "../services/workspace";

interface SettingsProps {
  onClose: () => void;
  currentWorkspace?: Workspace | null;
  theme: Theme;
  onToggleTheme: () => void;
  lang: Language;
  onChangeLang: (lang: Language) => void;
  t: any;
  onLogout: () => void | Promise<void>;
  onDeleteAccount?: () => void;
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
  const [memberCount, setMemberCount] = useState<number | null>(null);

  // 워크스페이스 멤버 수 실시간 조회
  useEffect(() => {
    async function fetchMemberCount() {
      if (!currentWorkspace?.id) return;
      const res = await getWorkspaceMembersApi(currentWorkspace.id);
      if (res.status === "success" && res.members) {
        setMemberCount(res.members.length);
      }
    }

    fetchMemberCount();
  }, [currentWorkspace?.id]);

  // 워크스페이스 정보
  const workspaceSectionItems = [
    {
      label: t.settings_workspace_name || "워크스페이스 이름",
      value: currentWorkspace?.name || "선택된 워크스페이스 없음",
    },
    {
      label: t.settings_member_count || "팀원 관리",
      value: memberCount !== null ? `${memberCount}명` : "불러오는 중...",
    },
  ];

  // 알림 설정
  const notificationSectionItems = [
    { label: t.settings_notif_new || "새 메시지 알림", value: t.settings_status_on || "켜짐" },
    { label: t.settings_notif_start || "회의 시작 알림", value: t.settings_status_on || "켜짐" },
    { label: t.settings_notif_contra || "모순 감지 알림", value: t.settings_status_on || "켜짐" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="flex h-[520px] w-[500px] flex-col rounded-2xl border border-recall-border bg-recall-bg text-recall-text shadow-2xl">
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-recall-border px-6 py-4">
          <p className="text-base font-bold">{t.settings_title || "설정"}</p>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-recall-textMuted hover:text-recall-text transition"
          >
            {t.btn_close || "닫기"}
          </button>
        </div>

        {/* 본문 스크롤 영역 */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* 1. 워크스페이스 구역 */}
          <div>
            <p className="mb-2 text-xs font-semibold text-recall-textMuted">
              {t.workspace || "워크스페이스"}
            </p>
            <div className="overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
              {workspaceSectionItems.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between border-b border-recall-border last:border-b-0 px-4 py-3 text-sm"
                >
                  <span className="text-recall-text font-medium">{item.label}</span>
                  <span className="text-recall-textMuted font-medium">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 2. 알림 구역 */}
          <div>
            <p className="mb-2 text-xs font-semibold text-recall-textMuted">
              {t.settings_notif || "알림"}
            </p>
            <div className="overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
              {notificationSectionItems.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between border-b border-recall-border last:border-b-0 px-4 py-3 text-sm"
                >
                  <span className="text-recall-text font-medium">{item.label}</span>
                  <span className="text-recall-textMuted">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 3. 화면 구역 */}
          <div>
            <p className="mb-2 text-xs font-semibold text-recall-textMuted">
              {t.settings_display || "화면"}
            </p>
            <div className="overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
              {/* 다크/라이트 모드 스위치 */}
              <button
                type="button"
                onClick={onToggleTheme}
                className="flex w-full items-center justify-between border-b border-recall-border px-4 py-3 text-sm hover:bg-white/5 transition"
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
                className="flex w-full items-center justify-between px-4 py-3 text-sm hover:bg-white/5 transition"
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
            <p className="mb-2 text-xs font-semibold text-recall-textMuted">
              계정 관리
            </p>
            <div className="overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
              <button
                type="button"
                onClick={() => {
                  if (window.confirm("정말로 탈퇴하시겠습니까? 계정의 모든 정보가 영구적으로 삭제됩니다.")) {
                    onClose();
                    if (onDeleteAccount) onDeleteAccount();
                    else onLogout();
                  }
                }}
                className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-recall-danger hover:bg-recall-danger/10 transition"
              >
                <span>회원 탈퇴</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}