import { useEffect, useState } from "react";
import {
  AppNotification,
  getNotificationListApi,
  markNotificationReadApi,
} from "../services/notification";

const POLL_INTERVAL_MS = 15000;

// 워크스페이스 알림함 - 목록 폴링 + 읽음 처리
export function useNotifications(workspaceId: string) {
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  // 초기값을 true로 둬야 한다 - false로 시작하면 첫 렌더에서(진짜 fetch가 끝나기도 전에)
  // NotificationBell이 "로딩 끝났다"고 착각해서 빈 목록을 기준점으로 잡아버리고,
  // 실제 데이터가 도착했을 때 기존 안 읽은 알림 전부를 "새로 도착"으로 오인해 토스트로 쏟아낸다.
  const [isLoading, setIsLoading] = useState(true);

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  async function loadList() {
    if (!workspaceId) return;
    const res = await getNotificationListApi(workspaceId);
    if (res.status === "success") {
      setNotifications(res.notifications);
    }
  }

  useEffect(() => {
    setIsLoading(true);
    loadList().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  // 새 알림을 놓치지 않도록 백그라운드에서 조용히 주기적 재조회 (로딩 스피너 없이)
  useEffect(() => {
    if (!workspaceId) return;
    const timer = setInterval(loadList, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  async function markRead(id: string) {
    // 낙관적 업데이트 — 서버 응답 기다리지 않고 바로 읽음 표시
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
    );
    const res = await markNotificationReadApi(workspaceId, id);
    if (res.status === "success" && res.notification) {
      const updated = res.notification;
      setNotifications((prev) => prev.map((n) => (n.id === id ? updated : n)));
    }
  }

  return {
    notifications,
    unreadCount,
    isLoading,
    markRead,
    refresh: loadList,
  };
}
