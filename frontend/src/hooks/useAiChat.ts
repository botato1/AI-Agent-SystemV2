import { useEffect, useRef, useState } from "react";
import {
  createAiChatSessionApi,
  getAiChatSessionsApi,
  updateAiChatSessionCategoryApi,
  createRoomAiChatSessionApi,
  getRoomAiChatSessionsApi,
  updateRoomAiChatSessionCategoryApi,
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

// roomId를 주면 그 채팅방 안에 묶인 AI Chat(room-scoped)을 쓰고, 안 주면 워크스페이스
// 단독 "AI 인사이트" 화면(standalone)을 쓴다 - 두 API 계약이 거의 동일해서 훅 하나로 분기한다.
export function useAiChat(workspaceId: string, selectedCategoryId?: string | null, roomId?: string) {
  const [sessions, setSessions] = useState<AIChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AiChatDisplayMessage[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);

  // sendMessage처럼 await 너머에서 "지금도 그 세션을 보고 있는지" 확인해야 하는
  // 곳에서 쓰는, 항상 최신값을 가리키는 ref (state는 클로저에 캡처된 시점 값이라 못 씀).
  const activeSessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  // 대화 목록 불러오기 - 최근 활동순으로 내려오므로 첫 번째를 기본 선택.
  // 단, 이미 선택된 대화가 목록에 여전히 존재하면 그 선택을 유지한다 - 그렇지 않으면
  // 메시지 전송 후 제목/정렬을 갱신하려고 부르는 것뿐인데 사용자가 보고 있던 대화가
  // 매번 목록 맨 앞으로 강제로 튕겨나가 버린다.
  async function loadSessions() {
    if (!workspaceId) return;

    setIsLoadingSessions(true);
    const res = roomId
      ? await getRoomAiChatSessionsApi(workspaceId, roomId)
      : await getAiChatSessionsApi(workspaceId);
    setIsLoadingSessions(false);

    if (res.status === "success") {
      setSessions(res.sessions);
      setActiveSessionId((prev) =>
        prev && res.sessions.some((s) => s.id === prev) ? prev : res.sessions[0]?.id ?? null
      );
    }
  }

  useEffect(() => {
    setActiveSessionId(null);
    setMessages([]);
    loadSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, roomId]);

  // 사이드바 카테고리 전환 시, 다른 카테고리 대화를 계속 열어둔 채로 보여주지 않게 선택을 초기화.
  useEffect(() => {
    setActiveSessionId(null);
    setMessages([]);
  }, [selectedCategoryId]);

  // 선택된 대화가 바뀌면 그 대화의 메시지 기록을 불러옴
  useEffect(() => {
    // 요청을 보낸 뒤 activeSessionId가 다시 바뀌면(빠른 세션 전환) 늦게 도착한
    // 이전 세션의 응답이 지금 보고 있는 세션의 메시지 목록을 덮어쓰지 않도록 막는다.
    let cancelled = false;

    async function loadMessages() {
      if (!workspaceId || !activeSessionId) {
        setMessages([]);
        return;
      }

      setIsLoadingMessages(true);
      const res = await getAiChatMessagesApi(workspaceId, activeSessionId);
      if (cancelled) return;
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
        // 근거자료가 없는 답변엔 "근거자료 보기" 버튼 자체를 숨기려면 있는지 여부를
        // 미리 알아야 하는데, 백엔드가 목록 응답에 개수를 안 내려줘서 메시지별로
        // 따로 조회해야 한다 - 답변마다 병렬로 미리 불러와둔다.
        res.messages
          .filter((m) => m.role === "assistant")
          .forEach((m) => fetchSources(m.id));
      }
    }

    loadMessages();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, activeSessionId]);

  function selectSession(sessionId: string) {
    setActiveSessionId(sessionId);
  }

  // 새 대화 생성 - 목록 맨 앞에 추가하고 바로 선택. categoryId를 주면 그 카테고리로 태깅된다
  // (사이드바에서 특정 카테고리를 선택한 채로 새 대화를 시작한 경우).
  async function createSession(categoryId?: string): Promise<string | null> {
    const res = roomId
      ? await createRoomAiChatSessionApi(workspaceId, roomId, categoryId)
      : await createAiChatSessionApi(workspaceId, categoryId);
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

  // 대화를 다른 카테고리로 옮기기
  async function changeSessionCategory(sessionId: string, categoryId: string): Promise<boolean> {
    const res = roomId
      ? await updateRoomAiChatSessionCategoryApi(workspaceId, roomId, sessionId, categoryId)
      : await updateAiChatSessionCategoryApi(workspaceId, sessionId, categoryId);
    if (res.status === "success" && res.session) {
      const updated = res.session;
      setSessions((prev) => prev.map((s) => (s.id === sessionId ? updated : s)));
      return true;
    }
    alert(`카테고리 변경 실패: ${res.message}`);
    return false;
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

    // 응답을 기다리는 동안 사용자가 다른 대화로 옮겨갔다면, 지금 화면에 떠 있는
    // messages 배열은 이 요청과 무관한 대화의 것이다 - 거기에 답변을 끼워넣으면
    // (assistantTempId를 못 찾아 조용히 무시되거나, 최악의 경우 엉뚱한 대화에 답이
    // 나타나는) 버그가 생긴다. 답변 자체는 이미 서버에 저장돼 있으니, 그 대화로
    // 돌아왔을 때 loadMessages가 다시 불러와 보여준다.
    const stillOnSameSession = activeSessionIdRef.current === sessionId;

    if (res.status === "success" && res.assistantMessage) {
      const assistant = res.assistantMessage;

      if (stillOnSameSession) {
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
        fetchSources(assistant.id);
      }

      // 첫 질문으로 대화 제목이 자동 생성되므로, 목록도 다시 불러와 제목/정렬을 맞춘다.
      // loadSessions는 이제 이미 선택된 대화를 강제로 바꾸지 않으므로 안전하다.
      loadSessions();
    } else if (stillOnSameSession) {
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
    changeSessionCategory,
    deleteSession,
    messages,
    isLoadingSessions,
    isLoadingMessages,
    isSending,
    sendMessage,
    fetchSources,
  };
}
