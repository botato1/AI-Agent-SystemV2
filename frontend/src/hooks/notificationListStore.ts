import {
  AppNotification,
  getNotificationListApi,
  getNotificationStreamTicketApi,
} from "../services/notification";

// NotificationBell과 useRealMeetings(meeting_summary_ready 알림 소비용)가 각자 독립적으로
// useNotifications()를 호출해서, 같은 워크스페이스를 보는 탭 하나에서도 알림 목록 폴링이
// 중복으로 나가고 있었다 - meetingListStore와 똑같은 문제라 똑같은 방식으로 고친다.
// 워크스페이스별로 연결을 하나만 두고, 구독자는 그 결과를 공유해서 받는다.
//
// 백엔드가 폴링 대신 /notifications/stream 웹소켓(티켓 발급 후 연결)을 지원하게 되면서,
// 이제는 주기적으로 찔러보는 대신 알림이 실제로 생성될 때(notification_created 이벤트)만
// 목록을 다시 받아온다 - meetingListStore와 동일한 패턴.

type Listener = (notifications: AppNotification[]) => void;

interface Entry {
  notifications: AppNotification[];
  listeners: Set<Listener>;
  socket: WebSocket | null;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  cancelled: boolean;
  inFlight: Promise<void> | null;
}

const RECONNECT_DELAY_MS = 3000;

const entries = new Map<string, Entry>();

function getEntry(workspaceId: string): Entry {
  let entry = entries.get(workspaceId);
  if (!entry) {
    entry = {
      notifications: [],
      listeners: new Set(),
      socket: null,
      reconnectTimer: null,
      cancelled: false,
      inFlight: null,
    };
    entries.set(workspaceId, entry);
  }
  return entry;
}

async function fetchAndNotify(workspaceId: string): Promise<void> {
  const entry = getEntry(workspaceId);
  if (entry.inFlight) return entry.inFlight;

  entry.inFlight = (async () => {
    const res = await getNotificationListApi(workspaceId);
    if (res.status === "success") {
      entry.notifications = res.notifications;
      entry.listeners.forEach((l) => l(entry.notifications));
    }
  })();

  try {
    await entry.inFlight;
  } finally {
    entry.inFlight = null;
  }
}

async function connect(workspaceId: string): Promise<void> {
  const entry = getEntry(workspaceId);

  const ticketRes = await getNotificationStreamTicketApi(workspaceId);
  if (entry.cancelled || ticketRes.status !== "success" || !ticketRes.wsTicket) {
    if (!entry.cancelled) {
      entry.reconnectTimer = setTimeout(() => connect(workspaceId), RECONNECT_DELAY_MS);
    }
    return;
  }

  const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  const socket = new WebSocket(
    `${wsBase}/api/workspaces/${workspaceId}/notifications/stream?ticket=${ticketRes.wsTicket}`
  );
  entry.socket = socket;

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.event === "notification_created") {
        fetchAndNotify(workspaceId);
      }
    } catch (error) {
      console.error("notification stream message parse error:", error);
    }
  };

  socket.onclose = (event) => {
    if (entry.cancelled) return;
    // 티켓 만료/무효(4401), 워크스페이스 없음(4404)이면 재연결해도 소용없다
    if (event.code === 4401 || event.code === 4404) return;
    entry.reconnectTimer = setTimeout(() => connect(workspaceId), RECONNECT_DELAY_MS);
  };
}

// 구독 시작 시 캐시된 값을 즉시 넘겨주고, 첫 구독자가 생길 때만 최초 조회 + 스트림 연결을
// 시작해서 마지막 구독자가 사라지면(해당 화면을 아무도 안 보고 있으면) 연결을 끊는다.
export function subscribeNotificationList(workspaceId: string, listener: Listener): () => void {
  const entry = getEntry(workspaceId);
  entry.listeners.add(listener);
  listener(entry.notifications);

  if (entry.listeners.size === 1) {
    entry.cancelled = false;
    fetchAndNotify(workspaceId);
    connect(workspaceId);
  }

  return () => {
    entry.listeners.delete(listener);
    if (entry.listeners.size === 0) {
      entry.cancelled = true;
      if (entry.reconnectTimer) clearTimeout(entry.reconnectTimer);
      entry.reconnectTimer = null;
      entry.socket?.close();
      entry.socket = null;
    }
  };
}

// markRead/삭제처럼 로컬에서 바로 결과를 아는 변경을 서버 이벤트를 기다리지 않고 모든
// 구독자(NotificationBell, useRealMeetings 둘 다)에게 즉시 반영하기 위한 캐시 갱신.
export function setNotificationListCache(
  workspaceId: string,
  updater: (prev: AppNotification[]) => AppNotification[]
): void {
  const entry = getEntry(workspaceId);
  entry.notifications = updater(entry.notifications);
  entry.listeners.forEach((l) => l(entry.notifications));
}

export function refreshNotificationList(workspaceId: string): Promise<void> {
  return fetchAndNotify(workspaceId);
}
