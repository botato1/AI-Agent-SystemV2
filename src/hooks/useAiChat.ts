import { useEffect, useState } from "react";
import {
  getOrCreateAiChatSessionApi,
  getAiChatMessagesApi,
  sendAiChatMessageApi,
  AIChatRole,
} from "../services/aiChat";

export interface AiChatDisplayMessage {
  id: string;
  role: AIChatRole;
  content: string;
  isPending?: boolean;
  errorText?: string;
}

// 채팅방별 AI Chat(RAG 질의응답) 실제 백엔드 연동
export function useAiChat(workspaceId: string, roomId: string) {
  const [messages, setMessages] = useState<AiChatDisplayMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    async function init() {
      if (!workspaceId || !roomId) return;

      setIsLoading(true);
      await getOrCreateAiChatSessionApi(workspaceId, roomId);
      const historyRes = await getAiChatMessagesApi(workspaceId, roomId);
      setIsLoading(false);

      if (historyRes.status === "success") {
        setMessages(historyRes.messages.map((m) => ({ id: m.id, role: m.role, content: m.content })));
      }
    }

    init();
  }, [workspaceId, roomId]);

  async function sendMessage(content: string) {
    const trimmed = content.trim();
    if (!trimmed) return;

    const tempId = crypto.randomUUID();
    setMessages((prev) => [...prev, { id: tempId, role: "user", content: trimmed, isPending: true }]);
    setIsSending(true);

    const res = await sendAiChatMessageApi(workspaceId, roomId, trimmed);
    setIsSending(false);

    if (res.status === "success" && res.assistantMessage) {
      const assistantMessage = res.assistantMessage;
      setMessages((prev) => [
        ...prev.map((m) => (m.id === tempId ? { ...m, isPending: false } : m)),
        { id: assistantMessage.id, role: assistantMessage.role, content: assistantMessage.content },
      ]);
    } else {
      // 실패하면 백엔드에도 아무것도 저장되지 않으므로, 화면에서도 실패 표시만 남기고 별도 처리 안 함
      setMessages((prev) =>
        prev.map((m) => (m.id === tempId ? { ...m, isPending: false, errorText: res.message } : m))
      );
    }
  }

  return { messages, isLoading, isSending, sendMessage };
}
