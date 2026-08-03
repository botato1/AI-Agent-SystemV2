import { useEffect, useState } from "react";
import {
  getOrCreateWorkspaceAiChatSessionApi,
  getWorkspaceAiChatMessagesApi,
  sendWorkspaceAiChatMessageApi,
  getWorkspaceAiMessageSourcesApi,
  AIChatRole,
  AIMessageSource,
} from "../services/aiChat";

export interface AiChatDisplayMessage {
  id: string;
  role: AIChatRole;
  content: string;
  modelName?: string | null;
  isPending?: boolean;
  errorText?: string;
  sources?: AIMessageSource[];
}

export function useAiChat(workspaceId: string) {
  const [messages, setMessages] = useState<AiChatDisplayMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);

  // 워크스페이스 AI 대화 내역 불러오기
  async function loadHistory() {
    if (!workspaceId) return;

    setIsLoading(true);
    await getOrCreateWorkspaceAiChatSessionApi(workspaceId);
    const historyRes = await getWorkspaceAiChatMessagesApi(workspaceId);
    setIsLoading(false);

    if (historyRes.status === "success") {
      setMessages(
        historyRes.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          modelName: m.model_name,
        }))
      );
    }
  }

  useEffect(() => {
    loadHistory();
  }, [workspaceId]);

  // 질문 전송
  async function sendMessage(content: string) {
    const trimmed = content.trim();
    if (!trimmed) return;

    const userTempId = crypto.randomUUID();
    const assistantTempId = crypto.randomUUID();

    // 사용자가 질문 입력 시 즉시 메시지 추가 및 임시 답변 대기(로딩) 노출
    setMessages((prev) => [
      ...prev,
      { id: userTempId, role: "user", content: trimmed },
      { id: assistantTempId, role: "assistant", content: "", isPending: true },
    ]);
    setIsSending(true);

    const res = await sendWorkspaceAiChatMessageApi(workspaceId, trimmed);
    setIsSending(false);

    if (res.status === "success" && res.assistantMessage) {
      const assistant = res.assistantMessage;

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantTempId
            ? {
                id: assistant.id,
                role: assistant.role,
                content: assistant.content,
                modelName: assistant.model_name,
                isPending: false,
              }
            : m
        )
      );
    } else {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantTempId
            ? {
                ...m,
                isPending: false,
                errorText: res.message || "답변을 가져오는 중 오류가 발생했습니다.",
              }
            : m
        )
      );
    }
  }

  // 특정 AI 답변의 근거 자료 조회
  async function fetchSources(messageId: string) {
    const res = await getWorkspaceAiMessageSourcesApi(workspaceId, messageId);
    if (res.status === "success") {
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, sources: res.sources } : m))
      );
    }
  }

  return { messages, isLoading, isSending, sendMessage, fetchSources };
}