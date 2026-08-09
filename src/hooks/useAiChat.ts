import { useEffect, useState } from "react";
import {
  createAiChatSessionApi,
  getAiChatSessionsApi,
  deleteAiChatSessionApi,
  sendAiChatMessageApi,
  getAiChatMessagesApi,
  getWorkspaceAiMessageSourcesApi,
  AIChatRole,
  AIChatSession,
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
  const [sessions, setSessions] = useState<AIChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AiChatDisplayMessage[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);

  // 대화 목록 불러오기 - 최근 활동순으로 내려오므로 첫 번째를 기본 선택
  async function loadSessions() {
    if (!workspaceId) return;

    setIsLoadingSessions(true);
    const res = await getAiChatSessionsApi(workspaceId);
    setIsLoadingSessions(false);

    if (res.status === "success") {
      setSessions(res.sessions);
      setActiveSessionId(res.sessions[0]?.id ?? null);
    }
  }

  useEffect(() => {
    setActiveSessionId(null);
    setMessages([]);
    loadSessions();
  }, [workspaceId]);

  // 선택된 대화가 바뀌면 그 대화의 메시지 기록을 불러옴
  useEffect(() => {
    async function loadMessages() {
      if (!workspaceId || !activeSessionId) {
        setMessages([]);
        return;
      }

      setIsLoadingMessages(true);
      const res = await getAiChatMessagesApi(workspaceId, activeSessionId);
      setIsLoadingMessages(false);

      if (res.status === "success") {
        setMessages(
          res.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            modelName: m.model_name,
          }))
        );
      }
    }

    loadMessages();
  }, [workspaceId, activeSessionId]);

  function selectSession(sessionId: string) {
    setActiveSessionId(sessionId);
  }

  // 새 대화 생성 - 목록 맨 앞에 추가하고 바로 선택
  async function createSession(): Promise<string | null> {
    const res = await createAiChatSessionApi(workspaceId);
    if (res.status === "success" && res.session) {
      const session = res.session;
      setSessions((prev) => [session, ...prev]);
      setActiveSessionId(session.id);
      setMessages([]);
      return session.id;
    }
    alert(`새 대화 생성 실패: ${res.message}`);
    return null;
  }

  async function deleteSession(sessionId: string) {
    const res = await deleteAiChatSessionApi(workspaceId, sessionId);
    if (res.status !== "success") {
      alert(`대화 삭제 실패: ${res.message}`);
      return;
    }

    const remaining = sessions.filter((s) => s.id !== sessionId);
    setSessions(remaining);
    if (activeSessionId === sessionId) {
      setActiveSessionId(remaining[0]?.id ?? null);
    }
  }

  // 질문 전송 - 선택된 대화가 없으면(새로 시작하는 경우) 먼저 세션을 만든 뒤 보낸다
  async function sendMessage(content: string) {
    const trimmed = content.trim();
    if (!trimmed) return;

    let sessionId = activeSessionId;
    if (!sessionId) {
      sessionId = await createSession();
      if (!sessionId) return;
    }

    const userTempId = crypto.randomUUID();
    const assistantTempId = crypto.randomUUID();

    setMessages((prev) => [
      ...prev,
      { id: userTempId, role: "user", content: trimmed },
      { id: assistantTempId, role: "assistant", content: "", isPending: true },
    ]);
    setIsSending(true);

    const res = await sendAiChatMessageApi(workspaceId, sessionId, trimmed);
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

      // 첫 질문으로 대화 제목이 자동 생성되므로, 목록도 다시 불러와 제목/정렬을 맞춘다
      loadSessions();
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

  return {
    sessions,
    activeSessionId,
    selectSession,
    createSession,
    deleteSession,
    messages,
    isLoadingSessions,
    isLoadingMessages,
    isSending,
    sendMessage,
    fetchSources,
  };
}
