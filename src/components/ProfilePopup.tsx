import { useState, useRef, useEffect } from "react";
import { User } from "../types";
import { Theme } from "../hooks/useTheme";
import { MoonIcon, SunIcon, ChevronDownIcon } from "./icons";
import Avatar from "./Avatar";

interface ProfilePopupProps {
  user: User;
  onOpenProfile: () => void;
  onOpenSettings: () => void;
  onLogout: () => void;
  theme: Theme;
  onToggleTheme: () => void;
  t: any; // 다국어 번역 객체 추가
}

export default function ProfilePopup({
  user,
  onOpenProfile,
  onOpenSettings,
  onLogout,
  theme,
  onToggleTheme,
  t, // props 구조 분해 할당 추가
}: ProfilePopupProps) {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 팝업 바깥을 클릭하면 닫히도록 처리
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // 한글 메뉴 텍스트를 t를 활용해 번역 처리
  const menuItems: { label: string; onClick: () => void }[] = [
    { label: t.profile_my_profile, onClick: onOpenProfile },
    { label: t.settings_title, onClick: onOpenSettings },
  ];

  // 유저의 온라인 상태 번역 헬퍼 함수
  function getStatusLabel(status: string) {
    if (status === "online") return t.profile_status_online;
    if (status === "away") return t.profile_status_away;
    return t.profile_status_offline;
  }

  return (
    <div ref={wrapperRef} className="relative mt-auto px-2 pb-2">
      {isOpen && (
        <div className="absolute bottom-14 left-2 right-2 rounded-xl border border-recall-border bg-recall-bgSoft p-1.5 shadow-lg z-20">
          {menuItems.map((item) => (
            <button
              key={item.label}
              onClick={() => {
                item.onClick();
                setIsOpen(false);
              }}
              className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm text-recall-text hover:bg-white/5"
            >
              {item.label}
            </button>
          ))}
          <button
            onClick={onToggleTheme}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-recall-text hover:bg-white/5"
          >
            {theme === "dark" ? <MoonIcon size={14} /> : <SunIcon size={14} />}
            {theme === "dark" ? t.settings_theme_dark : t.settings_theme_light}
          </button>
          <div className="my-1 border-t border-recall-border" />
          <button
            onClick={() => {
              onLogout();
              setIsOpen(false);
            }}
            className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm text-recall-danger hover:bg-white/5"
          >
            {t.logout}
          </button>
        </div>
      )}

      <button
        onClick={() => setIsOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg border border-recall-border p-2 hover:bg-white/5"
      >
        <Avatar user={user} size={28} />
        <div className="min-w-0 flex-1 text-left">
          <p className="truncate text-sm font-medium text-recall-text">{user.name}</p>
          <p className="truncate text-xs text-recall-textMuted">
            {getStatusLabel(user.status)}
          </p>
        </div>
        <span className="text-recall-textMuted">
          <ChevronDownIcon
            size={13}
            className={`flex-shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`}
          />
        </span>
      </button>
    </div>
  );
}