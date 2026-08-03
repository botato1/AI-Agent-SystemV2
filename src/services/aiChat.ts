import { authFetch } from "./auth";

// --- 타입 정의 ---
export type AIChatRole = "user" | "assistant" | "system";
export type AIMessageSourceType = "content_chunk" | "code_fact" | string;

export interface AIChatSession {
  id: string;
  workspace_id: string;
  room_id: string | null;
  user_id: string;
  title: string | null;
  created_at: string;
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
  created_at?: string;
}

export interface GetWorkspaceAiChatSessionResponse {
  status: "success" | "error";
  session: AIChatSession | null;
  message: string;
  error: string | null;
}

export interface SendWorkspaceAiChatMessageResponse {
  status: "success" | "error";
  assistantMessage: AIChatMessage | null;
  message: string;
  error: string | null;
}

export interface GetWorkspaceAiChatMessagesResponse {
  status: "success" | "error";
  messages: AIChatMessage[];
  message: string;
  error: string | null;
}

export interface GetWorkspaceAiMessageSourcesResponse {
  status: "success" | "error";
  sources: AIMessageSource[];
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// 워크스페이스 단독 AI Chat API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 워크스페이스 AI 세션 조회/생성 API (GET /api/workspaces/{workspace_id}/ai-chat/session)
 */
export async function getOrCreateWorkspaceAiChatSessionApi(
  workspaceId: string
): Promise<GetWorkspaceAiChatSessionResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/session`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "AI 세션을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 이용할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스입니다.";

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
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getOrCreateWorkspaceAiChatSessionApi error:", error);
    return {
      status: "error",
      session: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 질문 전송 + AI 답변 생성 API (POST /api/workspaces/{workspace_id}/ai-chat/messages)
 */
export async function sendWorkspaceAiChatMessageApi(
  workspaceId: string,
  content: string
): Promise<SendWorkspaceAiChatMessageResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      assistantMessage: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "AI 답변 생성에 실패했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 이용할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스입니다.";
      else if (response.status === 422) defaultMsg = "질문 내용을 입력해 주세요.";
      else if (response.status === 500) defaultMsg = "워크스페이스 기본 카테고리를 찾을 수 없습니다.";

      return {
        status: "error",
        assistantMessage: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      assistantMessage: data.assistant_message || data,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("sendWorkspaceAiChatMessageApi error:", error);
    return {
      status: "error",
      assistantMessage: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. AI 대화 기록 전체 시간순 조회 API (GET /api/workspaces/{workspace_id}/ai-chat/messages)
 */
export async function getWorkspaceAiChatMessagesApi(
  workspaceId: string
): Promise<GetWorkspaceAiChatMessagesResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/messages`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "AI 대화 기록을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스입니다.";

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
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getWorkspaceAiChatMessagesApi error:", error);
    return {
      status: "error",
      messages: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 특정 AI 답변 메시지의 근거 자료 조회 API (GET /api/workspaces/{workspace_id}/ai-chat/messages/{message_id}/sources)
 */
export async function getWorkspaceAiMessageSourcesApi(
  workspaceId: string,
  messageId: string
): Promise<GetWorkspaceAiMessageSourcesResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/messages/${messageId}/sources`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "근거자료를 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "메시지를 찾을 수 없거나 근거자료 조회 권한이 없습니다.";

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
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getWorkspaceAiMessageSourcesApi error:", error);
    return {
      status: "error",
      sources: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}