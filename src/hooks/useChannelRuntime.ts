import { useState } from "react";

export interface ChatMessage {
  id: string;
  author: string;
  text: string;
}

export interface DocItem {
  id: string;
  name: string;
  size: number;
  date: string;
  kind: "file" | "voice"; // 문서 업로드인지 음성 업로드인지 구분
}

interface ChannelRuntime {
  chatMessages: ChatMessage[];
  docs: DocItem[];
}

const EMPTY_RUNTIME: ChannelRuntime = { chatMessages: [], docs: [] };

function todayLabel(): string {
  const d = new Date();
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// 채널 id별로 채팅/문서 상태를 독립적으로 저장 - 채널을 바꿔도 서로 섞이지 않고,
// 같은 채널로 돌아오면 하던 대화·문서 그대로 이어짐
// (회의/녹음은 이제 채널이 아니라 카테고리 음성 허브 쪽에서 관리함)
// 문서는 "문서" 탭과 채팅창의 "+" 업로드가 같은 목록을 공유함
export function useChannelRuntime(channelId: string) {
  const [store, setStore] = useState<Record<string, ChannelRuntime>>({});

  const current: ChannelRuntime = store[channelId] ?? EMPTY_RUNTIME;

  function sendChatMessage(text: string) {
    setStore((prev) => ({
      ...prev,
      [channelId]: {
        ...(prev[channelId] ?? EMPTY_RUNTIME),
        chatMessages: [
          ...(prev[channelId] ?? EMPTY_RUNTIME).chatMessages,
          { id: crypto.randomUUID(), author: "나연", text },
        ],
      },
    }));
  }

  // 채팅창 "+"/드래그드롭이든 문서 탭 드래그앤드롭이든, 여기로 들어오면 같은 목록에 쌓임 (kind로 문서/음성 구분)
  // 채팅 쪽에서 올리면 "공유했습니다"라는 시스템 메시지도 같이 남김
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
      const label = kind === "voice" ? "음성 파일" : "문서";
      const chatMessages = announceInChat
        ? [
            ...prevRuntime.chatMessages,
            ...newDocs.map((doc) => ({
              id: crypto.randomUUID(),
              author: "나연",
              text: `${label}을 공유했습니다: ${doc.name}`,
            })),
          ]
        : prevRuntime.chatMessages;

      return {
        ...prev,
        [channelId]: {
          chatMessages,
          docs: [...newDocs, ...prevRuntime.docs],
        },
      };
    });
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
    chatMessages: current.chatMessages,
    docs: current.docs,
    sendChatMessage,
    addDocFiles,
    removeDoc,
  };
}