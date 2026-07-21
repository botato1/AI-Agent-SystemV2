// src/components/Settings.tsx
import { Language } from "../data/translations";
import { MoonIcon, SunIcon } from "./icons";
import { Theme } from "../hooks/useTheme";

interface SettingsProps {
  onClose: () => void;
  theme: Theme;
  onToggleTheme: () => void;
  lang: Language;
  onChangeLang: (lang: Language) => void;
  t: any;
}

export default function Settings({
  onClose,
  theme,
  onToggleTheme,
  lang,
  onChangeLang,
  t,
}: SettingsProps) {
  // 언어 설정과 화면 테마 설정을 일반 텍스트 목록 섹션에서 완전히 분리하여 설계
  const workspaceSectionItems = [
    { label: t.settings_workspace_name, value: t.settings_workspace_val },
    { label: t.settings_member_count, value: t.settings_members_val },
  ];

  const notificationSectionItems = [
    { label: t.settings_notif_new, value: t.settings_status_on },
    { label: t.settings_notif_start, value: t.settings_status_on },
    { label: t.settings_notif_contra, value: t.settings_status_on },
  ];

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/50">
      <div className="flex h-[480px] w-[550px] flex-col rounded-xl border border-recall-border bg-recall-bg text-recall-text">
        <div className="flex items-center justify-between border-b border-recall-border px-5 py-4">
          <p className="text-base font-medium">{t.settings_title}</p>
          <button
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-recall-textMuted hover:bg-white/5"
          >
            {t.btn_close}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* 1. 워크스페이스 관리 구역 */}
          <div>
            <p className="mb-2 text-xs font-medium text-recall-textMuted">{t.workspace}</p>
            <div className="overflow-hidden rounded-lg border border-recall-border bg-recall-bgSoft">
              {workspaceSectionItems.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between border-b border-recall-border last:border-b-0 px-3 py-2.5 text-sm"
                >
                  <span className="text-recall-text">{item.label}</span>
                  <span className="text-recall-textMuted">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 2. 알림 설정 구역 */}
          <div>
            <p className="mb-2 text-xs font-medium text-recall-textMuted">{t.settings_notif}</p>
            <div className="overflow-hidden rounded-lg border border-recall-border bg-recall-bgSoft">
              {notificationSectionItems.map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between border-b border-recall-border last:border-b-0 px-3 py-2.5 text-sm"
                >
                  <span className="text-recall-text">{item.label}</span>
                  <span className="text-recall-textMuted">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 3. 화면 및 언어 설정 구역 (중복 원천 차단) */}
          <div>
            <p className="mb-2 text-xs font-medium text-recall-textMuted">{t.settings_display}</p>
            <div className="overflow-hidden rounded-lg border border-recall-border bg-recall-bgSoft">
              {/* 다크/라이트 모드 스위치 */}
              <button
                onClick={onToggleTheme}
                className="flex w-full items-center justify-between border-b border-recall-border px-3 py-2.5 text-sm hover:bg-white/5"
              >
                <span className="flex items-center gap-2 text-recall-text">
                  {theme === "dark" ? <MoonIcon size={14} /> : <SunIcon size={14} />}
                  {theme === "dark" ? t.settings_theme_dark : t.settings_theme_light}
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

              {/* 언어 설정 토글 (오직 한 줄만 렌더링되도록 단순화!) */}
              <button
                onClick={() => onChangeLang(lang === "ko" ? "en" : "ko")}
                className="flex w-full items-center justify-between px-3 py-2.5 text-sm hover:bg-white/5"
              >
                <span className="text-recall-text">{t.settings_lang}</span>
                <span className="font-semibold text-recall-accent">
                  {lang === "ko" ? "한국어" : "English"}
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}