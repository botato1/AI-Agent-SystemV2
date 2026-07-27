import { authFetch } from "./auth";

// --- 타입 정의 ---

export type AIChatRole = "user" | "assistant" | "system";
export type AIMessageSourceType = "content_chunk" | "code_fact" | string;

export interface AIChatSession {
  id: string;
  workspace_id: string;
  room_id: string;
  user_id: string;
  title: string | null;
}

export interface AIChatMessage {
  id: string;
  session_id: string;
  role: AIChatRole;
  content: string;
  model_name?: string | null;
  created_at: string;
}

export interface AIMessageSource {
  id: string;
  ai_message_id: string;
  source_type: AIMessageSourceType;
  file_id: string;
  chunk_id?: string | null;
  code_fact_id?: string | null;
  similarity_score?: number | null;
  display_order: number;
  created_at: string;
}

export interface GetAiChatSessionResponse {
  status: "success" | "error";
  session: AIChatSession | null;
  message: string;
  error: string | null;
}

export interface SendAiChatMessageResponse {
  status: "success" | "error";
  assistantMessage: AIChatMessage | null;
  message: string;
  error: string | null;
  // 아직 RAG 그래프가 연결 안 된 경우 503으로 항상 실패한다 (백엔드 팀 확인 필요)
  isGraphNotReady: boolean;
}

export interface GetAiChatMessagesResponse {
  status: "success" | "error";
  messages: AIChatMessage[];
  message: string;
  error: string | null;
}

export interface GetAiMessageSourcesResponse {
  status: "success" | "error";
  sources: AIMessageSource[];
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. AI 채팅 세션 조회/생성 API (GET /api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat/session)
 */
export async function getOrCreateAiChatSessionApi(
  workspaceId: string,
  roomId: string
): Promise<GetAiChatSessionResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      session: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/ai-chat/session`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "AI 채팅 세션을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 이용할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 채팅방입니다.";
      }

      return {
        status: "error",
        session: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      session: data.session || data,
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getOrCreateAiChatSessionApi error:", error);
    return {
      status: "error",
      session: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 질문 전송 (AI 답변 생성) API (POST /api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat/messages)
 *
 * 주의: RAG 그래프가 아직 연결되지 않은 동안은 항상 503으로 실패하고, 이 경우 질문/답변 모두 저장되지 않는다.
 */
export async function sendAiChatMessageApi(
  workspaceId: string,
  roomId: string,
  content: string
): Promise<SendAiChatMessageResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      assistantMessage: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
      isGraphNotReady: false,
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/ai-chat/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      const isGraphNotReady = response.status === 503;
      let defaultMsg = "AI 답변 생성에 실패했습니다.";
      if (isGraphNotReady) {
        defaultMsg = "AI 답변 생성 기능은 아직 준비 중입니다.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 이용할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 채팅방입니다.";
      } else if (response.status === 422) {
        defaultMsg = "질문 내용을 입력해 주세요.";
      }

      return {
        status: "error",
        assistantMessage: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
        isGraphNotReady,
      };
    }

    return {
      status: "success",
      assistantMessage: data.assistant_message || data,
      message: data.message || "성공",
      error: null,
      isGraphNotReady: false,
    };
  } catch (error) {
    console.error("sendAiChatMessageApi error:", error);
    return {
      status: "error",
      assistantMessage: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
      isGraphNotReady: false,
    };
  }
}

/**
 * 3. AI 대화 기록 조회 API (GET /api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat/messages)
 */
export async function getAiChatMessagesApi(
  workspaceId: string,
  roomId: string
): Promise<GetAiChatMessagesResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      messages: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/ai-chat/messages`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "AI 대화 기록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "채팅방 또는 세션을 찾을 수 없습니다.";
      }

      return {
        status: "error",
        messages: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      messages: data.messages || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getAiChatMessagesApi error:", error);
    return {
      status: "error",
      messages: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. AI 메시지별 근거자료 조회 API
 * (GET /api/workspaces/{workspace_id}/rooms/{room_id}/ai-chat/messages/{message_id}/sources)
 */
export async function getAiMessageSourcesApi(
  workspaceId: string,
  roomId: string,
  messageId: string
): Promise<GetAiMessageSourcesResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      sources: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/ai-chat/messages/${messageId}/sources`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "근거자료를 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "메시지를 찾을 수 없습니다.";
      }

      return {
        status: "error",
        sources: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      sources: data.sources || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getAiMessageSourcesApi error:", error);
    return {
      status: "error",
      sources: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
