import { useEffect, useRef, useState } from "react";
import {
  getRoomMessagesApi,
  sendRoomMessageApi,
  deleteRoomMessageApi,
  getRoomStreamTicketApi,
  RoomMessage,
} from "../services/message";

export interface ChatMessage {
  id: string;
  author: string;
  senderId: string | null;
  text: string;
  isMine: boolean;
  createdAt: string;
}

// Case0(결정 리마인더) - contradiction_alert(Case2/3)와 달리 해결 대상이 아니라
// 가벼운 확인용 토스트로만 보여준다.
export interface DecisionReminderToast {
  id: string;
  statementText: string;
  displayMessage: string | null;
  decisionId: string | null;
}

export interface DocItem {
  id: string;
  name: string;
  size: number;
  statusLabel?: string; // 실제 문서 파일의 분석 상태 등, 파일 크기 대신 표시할 라벨
  date: string;
  kind: "file" | "voice"; // 문서 업로드인지 음성 업로드인지 구분
}

// 백엔드 응답 순서를 신뢰하지 않고 항상 실제 시간 순서(created_at 오름차순)로 정렬
function sortByCreatedAt(messages: RoomMessage[]): RoomMessage[] {
  return [...messages].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );
}

interface CurrentUserInfo {
  id: string;
  name: string;
}

// 채널 id별로 문서 상태를 독립적으로 저장 - 채널을 바꿔도 서로 섞이지 않고,
// 같은 채널로 돌아오면 하던 대화·문서 그대로 이어짐
// (회의/녹음은 이제 채널이 아니라 카테고리 음성 허브 쪽에서 관리함)
// 문서는 roomFiles(실제 업로드 API)가 관리하고, 음성은 실제 회의(Meeting) 업로드로 처리됨
// 채팅 메시지는 실제 백엔드(rooms/{room_id}/messages) 연동
export function useChannelRuntime(
  workspaceId: string,
  channelId: string,
  currentUser: CurrentUserInfo,
  memberNameById: Record<string, string>
) {
  const [roomMessages, setRoomMessages] = useState<RoomMessage[]>([]);
  const [decisionReminders, setDecisionReminders] = useState<DecisionReminderToast[]>([]);

  // 채널 전환 시 실제 메시지 히스토리 조회
  useEffect(() => {
    async function loadMessages() {
      setDecisionReminders([]);
      if (!workspaceId || !channelId) {
        setRoomMessages([]);
        return;
      }

      const res = await getRoomMessagesApi(workspaceId, channelId);
      if (res.status === "success") {
        setRoomMessages(sortByCreatedAt(res.messages));
      }
    }

    loadMessages();
  }, [workspaceId, channelId]);

  // 채널 전환 시 실시간 수신용 WebSocket 연결 (상대방이 보낸 메시지를 새로고침 없이 반영)
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!workspaceId || !channelId) return;

    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    async function connect() {
      const ticketRes = await getRoomStreamTicketApi(workspaceId, channelId);
      if (cancelled || ticketRes.status !== "success" || !ticketRes.wsTicket) return;

      const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;
      const wsBase = API_BASE_URL.replace(/^http/, "ws");
      const socket = new WebSocket(
        `${wsBase}/api/workspaces/${workspaceId}/rooms/${channelId}/stream?ticket=${ticketRes.wsTicket}`
      );
      socketRef.current = socket;

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "new_message" && payload.message) {
            const incoming = payload.message as RoomMessage;
            setRoomMessages((prev) =>
              prev.some((m) => m.id === incoming.id)
                ? prev
                : sortByCreatedAt([...prev, incoming])
            );
          } else if (payload.type === "decision_reminder") {
            const toast: DecisionReminderToast = {
              id: payload.decision_id ? `reminder-${payload.decision_id}` : `reminder-${crypto.randomUUID()}`,
              statementText: payload.statement_text || "",
              displayMessage: payload.display_message || null,
              decisionId: payload.decision_id || null,
            };
            setDecisionReminders((prev) =>
              prev.some((r) => r.id === toast.id) ? prev : [...prev, toast]
            );
          }
        } catch (error) {
          console.error("chat stream message parse error:", error);
        }
      };

      socket.onclose = (event) => {
        if (cancelled) return;
        // 티켓 만료/무효(4401), 채팅방 없음(4404)이면 재연결해도 소용없으니 시도하지 않음
        if (event.code === 4401 || event.code === 4404) return;
        reconnectTimer = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [workspaceId, channelId]);

  function resolveAuthor(senderUserId: string | null): string {
    if (senderUserId === currentUser.id) return currentUser.name;
    if (senderUserId && memberNameById[senderUserId]) return memberNameById[senderUserId];
    return "알 수 없음";
  }

  const chatMessages: ChatMessage[] = roomMessages.map((m) => ({
    id: m.id,
    author: resolveAuthor(m.sender_user_id),
    senderId: m.sender_user_id,
    text: m.content,
    isMine: m.sender_user_id === currentUser.id,
    createdAt: m.created_at,
  }));

  async function sendChatMessage(text: string) {
    if (!text.trim() || !workspaceId || !channelId) return;

    const res = await sendRoomMessageApi(workspaceId, channelId, text);

    if (res.status === "success" && res.messageData) {
      const sent = res.messageData as RoomMessage;
      // WS로 같은 메시지가 먼저 도착했을 수 있으니 id 기준으로 중복 방지
      setRoomMessages((prev) =>
        prev.some((m) => m.id === sent.id) ? prev : sortByCreatedAt([...prev, sent])
      );
    } else {
      alert(`메시지 전송 실패: ${res.message}`);
    }
  }

  async function deleteMessage(messageId: string) {
    if (!workspaceId || !channelId) return;

    const res = await deleteRoomMessageApi(workspaceId, channelId, messageId);

    if (res.status === "success") {
      setRoomMessages((prev) => prev.filter((m) => m.id !== messageId));
    } else {
      alert(`메시지 삭제 실패: ${res.message}`);
    }
  }

  function dismissDecisionReminder(id: string) {
    setDecisionReminders((prev) => prev.filter((r) => r.id !== id));
  }

  return {
    chatMessages,
    sendChatMessage,
    deleteMessage,
    decisionReminders,
    dismissDecisionReminder,
  };
}
