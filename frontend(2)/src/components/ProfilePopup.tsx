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
}

// Ver2에서 만들었던 사이드바 프로필 팝업과 동일한 패턴:
// isOpen state로 토글, 바깥 클릭하면 자동으로 닫힘 (useRef + click 이벤트로 감지)
export default function ProfilePopup({
  user,
  onOpenProfile,
  onOpenSettings,
  onLogout,
  theme,
  onToggleTheme,
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

  // 아이콘 없이 텍스트 라벨만 사용 (리스트형)
  // 내 프로필 = 계정 정보 전용 작은 모달, 설정 = 워크스페이스/알림/화면 모달
  const menuItems: { label: string; onClick: () => void }[] = [
    { label: "내 프로필", onClick: onOpenProfile },
    { label: "설정", onClick: onOpenSettings },
  ];

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
            {theme === "dark" ? "다크 모드" : "라이트 모드"}
          </button>
          <div className="my-1 border-t border-recall-border" />
          <button
            onClick={() => {
              onLogout();
              setIsOpen(false);
            }}
            className="flex w-full items-center rounded-lg px-2.5 py-2 text-left text-sm text-recall-danger hover:bg-white/5"
          >
            로그아웃
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
            {user.status === "online" ? "온라인" : user.status === "away" ? "자리비움" : "오프라인"}
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