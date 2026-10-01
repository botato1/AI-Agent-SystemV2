import { useEffect, useState } from "react";
import { AppNotification, markNotificationReadApi, deleteNotificationApi } from "../services/notification";
import {
  subscribeNotificationList,
  setNotificationListCache,
  refreshNotificationList,
} from "./notificationListStore";

// 워크스페이스 알림함 - 목록 폴링(워크스페이스당 공유 폴링 하나로 통합, notificationListStore
// 참고) + 읽음 처리
export function useNotifications(workspaceId: string) {
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  // 초기값을 true로 둬야 한다 - false로 시작하면 첫 렌더에서(진짜 fetch가 끝나기도 전에)
  // NotificationBell이 "로딩 끝났다"고 착각해서 빈 목록을 기준점으로 잡아버리고,
  // 실제 데이터가 도착했을 때 기존 안 읽은 알림 전부를 "새로 도착"으로 오인해 토스트로 쏟아낸다.
  const [isLoading, setIsLoading] = useState(true);

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  useEffect(() => {
    if (!workspaceId) return;
    setIsLoading(true);
    const unsubscribe = subscribeNotificationList(workspaceId, (list) => {
      setNotifications(list);
      setIsLoading(false);
    });
    return unsubscribe;
  }, [workspaceId]);

  async function markRead(id: string) {
    // 낙관적 업데이트 — 서버 응답 기다리지 않고 바로 읽음 표시 (공유 캐시에 반영해서
    // NotificationBell/useRealMeetings 등 다른 구독자도 즉시 같이 반영됨)
    setNotificationListCache(workspaceId, (prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
    );
    const res = await markNotificationReadApi(workspaceId, id);
    if (res.status === "success" && res.notification) {
      const updated = res.notification;
      setNotificationListCache(workspaceId, (prev) => prev.map((n) => (n.id === id ? updated : n)));
    }
  }

  // 이제 진짜 삭제 API가 있어서, 더 이상 로컬에서 숨기기만 하는 게 아니라 서버 row 자체를
  // 지운다. 낙관적으로 캐시에서 먼저 빼서 바로 사라지게 하고, 실패하면 다음 이벤트/새로고침
  // 때 다시 채워진다.
  async function deleteNotification(id: string) {
    setNotificationListCache(workspaceId, (prev) => prev.filter((n) => n.id !== id));
    await deleteNotificationApi(workspaceId, id);
  }

  return {
    notifications,
    unreadCount,
    isLoading,
    markRead,
    deleteNotification,
    refresh: () => refreshNotificationList(workspaceId),
  };
}
