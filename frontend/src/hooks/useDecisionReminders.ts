import { useEffect, useState } from "react";
import { getNotificationListApi, markNotificationReadApi, AppNotification } from "../services/notification";

const POLL_INTERVAL_MS = 8000;

// 리마인더(Case0)는 실시간 토스트(6초 자동소멸)만으로는 놓치면 그대로 사라져버려서,
// 모순 목록처럼 계속 남아있는 목록도 같이 둔다. notifications 테이블에 이미 기록돼 있으니
// 워크스페이스 알림 목록을 가져와 decision_reminder 타입만 걸러서 쓴다.
export function useDecisionReminders(workspaceId: string) {
  const [reminders, setReminders] = useState<AppNotification[]>([]);

  useEffect(() => {
    if (!workspaceId) {
      setReminders([]);
      return;
    }

    let cancelled = false;

    async function load() {
      const res = await getNotificationListApi(workspaceId);
      if (!cancelled && res.status === "success") {
        setReminders(res.notifications.filter((n) => n.type === "decision_reminder"));
      }
    }

    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [workspaceId]);

  async function markRead(notificationId: string) {
    const res = await markNotificationReadApi(workspaceId, notificationId);
    if (res.status === "success") {
      setReminders((prev) => prev.map((r) => (r.id === notificationId ? { ...r, is_read: true } : r)));
    }
  }

  return { reminders, markRead };
}
