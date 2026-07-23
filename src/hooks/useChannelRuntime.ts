import { useEffect, useState } from "react";
import {
  getRoomMessagesApi,
  sendRoomMessageApi,
  deleteRoomMessageApi,
  RoomMessage,
} from "../services/message";

export interface ChatMessage {
  id: string;
  author: string;
  text: string;
  isMine: boolean;
}

export interface DocItem {
  id: string;
  name: string;
  size: number;
  date: string;
  kind: "file" | "voice"; // 문서 업로드인지 음성 업로드인지 구분
}

interface ChannelRuntime {
  docs: DocItem[];
}

const EMPTY_RUNTIME: ChannelRuntime = { docs: [] };

function todayLabel(): string {
  const d = new Date();
  return `${d.getMonth() + 1}/${d.getDate()}`;
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
// 문서는 "문서" 탭과 채팅창의 "+" 업로드가 같은 목록을 공유함 (아직 로컬 mock)
// 채팅 메시지는 실제 백엔드(rooms/{room_id}/messages) 연동
export function useChannelRuntime(
  workspaceId: string,
  channelId: string,
  currentUser: CurrentUserInfo,
  memberNameById: Record<string, string>
) {
  const [store, setStore] = useState<Record<string, ChannelRuntime>>({});
  const [roomMessages, setRoomMessages] = useState<RoomMessage[]>([]);

  const current: ChannelRuntime = store[channelId] ?? EMPTY_RUNTIME;

  // 채널 전환 시 실제 메시지 히스토리 조회
  useEffect(() => {
    async function loadMessages() {
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

  function resolveAuthor(senderUserId: string | null): string {
    if (senderUserId === currentUser.id) return currentUser.name;
    if (senderUserId && memberNameById[senderUserId]) return memberNameById[senderUserId];
    return "알 수 없음";
  }

  const chatMessages: ChatMessage[] = roomMessages.map((m) => ({
    id: m.id,
    author: resolveAuthor(m.sender_user_id),
    text: m.content,
    isMine: m.sender_user_id === currentUser.id,
  }));

  async function sendChatMessage(text: string) {
    if (!text.trim() || !workspaceId || !channelId) return;

    const res = await sendRoomMessageApi(workspaceId, channelId, text);

    if (res.status === "success" && res.messageData) {
      setRoomMessages((prev) => sortByCreatedAt([...prev, res.messageData as RoomMessage]));
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

  // 채팅창 "+"/드래그드롭이든 문서 탭 드래그앤드롭이든, 여기로 들어오면 같은 목록에 쌓임 (kind로 문서/음성 구분)
  function addDocFiles(files: FileList | File[] | null, kind: "file" | "voice", announceInChat = false) {
    if (!files || files.length === 0) return;
    const fileArray = Array.from(files);
    const newDocs: DocItem[] = fileArray.map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size,
      date: todayLabel(),
      kind,
    }));

    setStore((prev) => {
      const prevRuntime = prev[channelId] ?? EMPTY_RUNTIME;
      return {
        ...prev,
        [channelId]: {
          docs: [...newDocs, ...prevRuntime.docs],
        },
      };
    });

    if (announceInChat) {
      const label = kind === "voice" ? "음성 파일" : "문서";
      newDocs.forEach((doc) => sendChatMessage(`${label}을 공유했습니다: ${doc.name}`));
    }
  }

  function removeDoc(docId: string) {
    setStore((prev) => ({
      ...prev,
      [channelId]: {
        ...(prev[channelId] ?? EMPTY_RUNTIME),
        docs: (prev[channelId] ?? EMPTY_RUNTIME).docs.filter((d) => d.id !== docId),
      },
    }));
  }

  return {
    chatMessages,
    docs: current.docs,
    sendChatMessage,
    deleteMessage,
    addDocFiles,
    removeDoc,
  };
}
