import { Meeting, getMeetingListApi, getMeetingListStreamTicketApi } from "../services/meeting";

// useLiveMeeting(참가 가능 회의 확인)과 useRealMeetings(HomeView/MeetingsPanel에서 각각 생성)가
// 전부 독립적으로 5초 폴링을 돌려서, 같은 워크스페이스를 보는 탭 하나에서도 getMeetingListApi가
// 중복 호출되고 사용자 수만큼 그대로 곱해지는 문제가 있었다. 워크스페이스별로 연결을 하나만
// 두고, 구독자(위 훅들)는 그 결과를 공유해서 받아가는 구조로 바꿔 중복 호출을 없앤다.
//
// 백엔드가 폴링 대신 /meetings/stream 웹소켓(티켓 발급 후 연결)을 지원하게 되면서, 이제는
// 주기적으로 찔러보는 대신 회의 상태가 실제로 바뀔 때(meeting_updated 이벤트)만 목록을
// 다시 받아온다 - rooms/documents stream과 동일한 패턴(useChannelRuntime.ts 참고).

type Listener = (meetings: Meeting[]) => void;

interface Entry {
  meetings: Meeting[];
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
      meetings: [],
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
    const res = await getMeetingListApi(workspaceId);
    if (res.status === "success") {
      entry.meetings = res.meetings;
      entry.listeners.forEach((l) => l(entry.meetings));
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

  const ticketRes = await getMeetingListStreamTicketApi(workspaceId);
  if (entry.cancelled || ticketRes.status !== "success" || !ticketRes.wsTicket) {
    if (!entry.cancelled) {
      entry.reconnectTimer = setTimeout(() => connect(workspaceId), RECONNECT_DELAY_MS);
    }
    return;
  }

  const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  const socket = new WebSocket(
    `${wsBase}/api/workspaces/${workspaceId}/meetings/stream?ticket=${ticketRes.wsTicket}`
  );
  entry.socket = socket;

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.event === "meeting_updated") {
        fetchAndNotify(workspaceId);
      }
    } catch (error) {
      console.error("meeting stream message parse error:", error);
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
export function subscribeMeetingsList(workspaceId: string, listener: Listener): () => void {
  const entry = getEntry(workspaceId);
  entry.listeners.add(listener);
  listener(entry.meetings);

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

// 회의 생성/삭제/수정 등 로컬에서 바로 결과를 아는 액션 직후, 서버 이벤트를 기다리지 않고
// 모든 구독자(다른 화면도)에게 즉시 반영하기 위한 낙관적 캐시 갱신.
export function setMeetingsListCache(
  workspaceId: string,
  updater: (prev: Meeting[]) => Meeting[]
): void {
  const entry = getEntry(workspaceId);
  entry.meetings = updater(entry.meetings);
  entry.listeners.forEach((l) => l(entry.meetings));
}

export function refreshMeetingsList(workspaceId: string): Promise<void> {
  return fetchAndNotify(workspaceId);
}
