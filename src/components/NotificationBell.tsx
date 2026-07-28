import { useEffect, useRef, useState } from "react";
import { useNotifications } from "../hooks/useNotifications";
import { AppNotification, NotificationType } from "../services/notification";
import {
  BellIcon,
  WarningIcon,
  CheckIcon,
  DocumentIcon,
  MicIcon,
  ClockIcon,
  RepeatIcon,
} from "./icons";

interface NotificationBellProps {
  workspaceId: string;
}

const TYPE_META: Record<NotificationType, { label: string; icon: typeof BellIcon; className: string }> = {
  decision_reminder: { label: "결정 리마인더", icon: ClockIcon, className: "text-recall-accent" },
  repeat_discussion: { label: "반복 논의", icon: RepeatIcon, className: "text-recall-accent" },
  document_recommendation: { label: "문서 추천", icon: DocumentIcon, className: "text-recall-textMuted" },
  contradiction_detected: { label: "모순 감지", icon: WarningIcon, className: "text-recall-danger" },
  contradiction_resolved: { label: "모순 해결", icon: CheckIcon, className: "text-emerald-400" },
  meeting_summary_ready: { label: "회의 요약 완료", icon: MicIcon, className: "text-recall-textMuted" },
  file_analysis_completed: { label: "파일 분석 완료", icon: CheckIcon, className: "text-emerald-400" },
  file_analysis_failed: { label: "파일 분석 실패", icon: WarningIcon, className: "text-recall-danger" },
};

function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "방금 전";
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}시간 전`;
  const diffDay = Math.floor(diffHour / 24);
  return `${diffDay}일 전`;
}

export default function NotificationBell({ workspaceId }: NotificationBellProps) {
  const { notifications, unreadCount, isLoading, markRead } = useNotifications(workspaceId);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  function handleItemClick(n: AppNotification) {
    if (!n.is_read) markRead(n.id);
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setIsOpen((v) => !v)}
        title="알림"
        className="relative flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
      >
        <BellIcon size={17} />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-recall-danger px-1 text-[10px] font-semibold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute bottom-full left-0 z-50 mb-2 flex max-h-96 w-80 flex-col rounded-xl border border-recall-border bg-recall-bgSoft shadow-2xl">
          <div className="flex items-center justify-between border-b border-recall-border px-3 py-2.5">
            <p className="text-sm font-semibold text-recall-text">알림</p>
            {unreadCount > 0 && <p className="text-xs text-recall-textMuted">{unreadCount}개 안 읽음</p>}
          </div>

          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <p className="p-4 text-center text-sm text-recall-textMuted">불러오는 중...</p>
            ) : notifications.length === 0 ? (
              <p className="p-4 text-center text-sm text-recall-textMuted">알림이 없습니다.</p>
            ) : (
              notifications.map((n) => {
                const meta = TYPE_META[n.type];
                const Icon = meta?.icon || BellIcon;
                return (
                  <button
                    key={n.id}
                    onClick={() => handleItemClick(n)}
                    className={`flex w-full items-start gap-2.5 border-b border-recall-border/60 px-3 py-2.5 text-left last:border-b-0 hover:bg-white/5 ${
                      n.is_read ? "opacity-60" : ""
                    }`}
                  >
                    <Icon size={15} className={`mt-0.5 flex-shrink-0 ${meta?.className || "text-recall-textMuted"}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        {!n.is_read && (
                          <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-accent" />
                        )}
                        <p className="truncate text-sm font-medium text-recall-text">{n.title}</p>
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-xs text-recall-textMuted">{n.message}</p>
                      <p className="mt-1 text-[11px] text-recall-textMuted">{formatRelativeTime(n.created_at)}</p>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
