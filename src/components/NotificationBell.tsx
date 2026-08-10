import { useEffect, useRef, useState } from "react";
import { useNotifications } from "../hooks/useNotifications";
import { AppNotification, NotificationType } from "../services/notification";
import { parseDisplayMessage, parseDecisionMessage } from "../lib/parseContradictionMessage";
import { Channel } from "../types";
import { PlaceholderKey } from "./Sidebar";
import {
  BellIcon,
  WarningIcon,
  AssistIcon,
  CheckIcon,
  DocumentIcon,
  MicIcon,
  ClockIcon,
  RepeatIcon,
  CloseIcon,
} from "./icons";

interface NotificationBellProps {
  workspaceId: string;
  channels: Channel[];
  onSelectChannel: (channel: Channel) => void;
  onSelectPlaceholder: (key: PlaceholderKey) => void;
}

const TYPE_META: Record<NotificationType, { label: string; icon: typeof BellIcon; className: string }> = {
  decision_reminder: { label: "결정 리마인더", icon: ClockIcon, className: "text-recall-accent" },
  repeat_discussion: { label: "반복 논의", icon: RepeatIcon, className: "text-recall-accent" },
  document_recommendation: { label: "문서 추천", icon: DocumentIcon, className: "text-recall-textMuted" },
  contradiction_detected: { label: "회의 도움", icon: AssistIcon, className: "text-recall-accent" },
  contradiction_resolved: { label: "회의 도움 해결", icon: CheckIcon, className: "text-emerald-400" },
  meeting_summary_ready: { label: "회의 요약 완료", icon: MicIcon, className: "text-recall-textMuted" },
  file_analysis_completed: { label: "파일 분석 완료", icon: CheckIcon, className: "text-emerald-400" },
  file_analysis_failed: { label: "파일 분석 실패", icon: WarningIcon, className: "text-recall-danger" },
};

// 읽은 알림을 화면에서 치우기 전까지 보여주는 시간 - 바로 사라지면 "읽음" 표시를
// 확인할 새도 없이 없어져서, 잠깐 흐리게 보여준 뒤에 치운다.
const HIDE_AFTER_READ_MS = 3000;

// 백엔드가 datetime 객체를 문자열로 그대로 박아 넣어서(마이크로초+타임존까지) 문장에
// "2026-08-05 08:22:20.831488+00:00" 같은 원본 타임스탬프가 섞여 나오는 경우가 있다.
// 사람이 읽을 땐 날짜 정도만 있으면 충분하므로, 이런 패턴을 찾아 "YYYY.M.D"로 바꿔치기한다.
const RAW_TIMESTAMP_PATTERN = /\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?/g;

function stripRawTimestamps(message: string): string {
  return message.replace(RAW_TIMESTAMP_PATTERN, (match) => {
    const date = new Date(match);
    if (Number.isNaN(date.getTime())) return match;
    return `${date.getFullYear()}.${date.getMonth() + 1}.${date.getDate()}`;
  });
}

// 모순 관련 알림의 message는 백엔드가 한 문장으로 뭉쳐서 내려주는 원문이라, 좁은 드롭다운에서도
// 최소한 "기존 → 새 발언"이 줄바꿈으로 구분되게 다듬는다. 패턴이 안 맞으면 원문을 그대로 둔다.
function formatNotificationMessage(n: AppNotification): string {
  if (n.type === "contradiction_detected" || n.type === "contradiction_resolved") {
    const parsed = parseDisplayMessage(n.message);
    if (parsed) return `기존: ${parsed.existingContent}\n새 발언: ${parsed.newStatement}`;

    const decisionParsed = parseDecisionMessage(n.message);
    if (decisionParsed) {
      return `${decisionParsed.headline}\n기존: ${decisionParsed.existingContent}\n새 발언: ${decisionParsed.newStatement}\n사유: ${decisionParsed.reason}`;
    }
  }

  return stripRawTimestamps(n.message);
}

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

// 알림 종류/참조 정보로 "관련 내용"이 어딘지 판단한다. room_id가 있으면 그 채팅방이
// 제일 정확한 목적지이고, 없으면 알림 종류에 맞는 화면으로 대략 안내한다.
function resolveNavigateTarget(
  n: AppNotification
): { kind: "channel"; roomId: string } | { kind: "placeholder"; key: PlaceholderKey } | null {
  if (n.room_id) return { kind: "channel", roomId: n.room_id };
  if (n.ref_type === "meeting_segment") return { kind: "placeholder", key: "voiceMeeting" };
  if (n.type === "document_recommendation" || n.type === "file_analysis_completed" || n.type === "file_analysis_failed") {
    return { kind: "placeholder", key: "docAnalysis" };
  }
  if (n.type === "meeting_summary_ready" || n.type === "decision_reminder" || n.type === "repeat_discussion") {
    return { kind: "placeholder", key: "voiceMeeting" };
  }
  return null;
}

export default function NotificationBell({
  workspaceId,
  channels,
  onSelectChannel,
  onSelectPlaceholder,
}: NotificationBellProps) {
  const { notifications, unreadCount, isLoading, markRead } = useNotifications(workspaceId);
  const [isOpen, setIsOpen] = useState(false);
  // 이번 세션에서 클릭해서 읽음 처리된 것들만 잠깐 보여주고 치운다. 예전부터 읽혀있던
  // 알림은(서버가 처음부터 is_read=true로 내려준 것) 애초에 목록에 안 보이게 한다.
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const hideTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
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

  useEffect(() => {
    const timers = hideTimersRef.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
    };
  }, []);

  function scheduleHide(id: string) {
    if (hideTimersRef.current.has(id)) return;
    const timer = setTimeout(() => {
      setHiddenIds((prev) => new Set(prev).add(id));
      hideTimersRef.current.delete(id);
    }, HIDE_AFTER_READ_MS);
    hideTimersRef.current.set(id, timer);
  }

  function dismiss(n: AppNotification) {
    const timer = hideTimersRef.current.get(n.id);
    if (timer) clearTimeout(timer);
    hideTimersRef.current.delete(n.id);
    setHiddenIds((prev) => new Set(prev).add(n.id));
    // 안 읽은 채로 지우면 읽음 카운트랑 안 맞으니, 지울 때 읽음 처리도 같이 한다
    if (!n.is_read) markRead(n.id);
  }

  function handleItemClick(n: AppNotification) {
    if (!n.is_read) {
      markRead(n.id);
      scheduleHide(n.id);
    }

    const target = resolveNavigateTarget(n);
    if (target?.kind === "channel") {
      const channel = channels.find((c) => c.id === target.roomId);
      if (channel) onSelectChannel(channel);
    } else if (target?.kind === "placeholder") {
      onSelectPlaceholder(target.key);
    }
    if (target) setIsOpen(false);
  }

  // 예전부터 읽혀있던 알림(이번 세션에서 안 읽음->읽음으로 안 바뀐 것)은 처음부터 숨긴다
  const visibleNotifications = notifications.filter((n) => (n.is_read ? hideTimersRef.current.has(n.id) : true) && !hiddenIds.has(n.id));

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
            ) : visibleNotifications.length === 0 ? (
              <p className="p-4 text-center text-sm text-recall-textMuted">알림이 없습니다.</p>
            ) : (
              visibleNotifications.map((n) => {
                const meta = TYPE_META[n.type];
                const Icon = meta?.icon || BellIcon;
                const canNavigate = !!resolveNavigateTarget(n);
                // 모순 관련 알림은 백엔드가 아직 예전 용어("모순 감지" 등)로 title을 내려주므로,
                // 순화된 명칭("회의 도움")으로 화면에서 덮어써서 보여준다. 그 외 타입은 백엔드
                // title을 그대로 신뢰한다(더 구체적인 문구일 수 있어서).
                const title =
                  n.type === "contradiction_detected" || n.type === "contradiction_resolved"
                    ? meta.label
                    : n.title;
                return (
                  <div
                    key={n.id}
                    className={`group flex w-full items-start gap-2.5 border-b border-recall-border/60 px-3 py-2.5 last:border-b-0 hover:bg-white/5 ${
                      n.is_read ? "opacity-60" : ""
                    }`}
                  >
                    <button
                      onClick={() => handleItemClick(n)}
                      title={canNavigate ? "관련 내용으로 이동" : undefined}
                      className="flex min-w-0 flex-1 items-start gap-2.5 text-left"
                    >
                      <Icon size={15} className={`mt-0.5 flex-shrink-0 ${meta?.className || "text-recall-textMuted"}`} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          {!n.is_read && (
                            <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-accent" />
                          )}
                          <p className="truncate text-sm font-medium text-recall-text">{title}</p>
                        </div>
                        <p className="mt-0.5 whitespace-pre-line text-xs text-recall-textMuted">
                          {formatNotificationMessage(n)}
                        </p>
                        <p className="mt-1 text-[11px] text-recall-textMuted">{formatRelativeTime(n.created_at)}</p>
                      </div>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        dismiss(n);
                      }}
                      title="목록에서 지우기"
                      className="mt-0.5 flex-shrink-0 text-recall-textMuted opacity-0 hover:text-recall-text group-hover:opacity-100"
                    >
                      <CloseIcon size={13} />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
