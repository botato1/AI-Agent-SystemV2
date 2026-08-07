import { authFetch } from "./auth";

// --- 타입 정의 ---
export type AIChatRole = "user" | "assistant" | "system";
export type AIMessageSourceType = "content_chunk" | "code_fact" | "decision" | string;

export interface AIChatSession {
  id: string;
  workspace_id: string;
  room_id: string | null;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
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
  // 결정사항(decision) 타입 소스는 파일에 속하지 않아 null로 내려온다.
  file_name: string | null;
  chunk_id?: string | null;
  code_fact_id?: string | null;
  similarity_score?: number | null;
  display_order: number;
  created_at?: string;
}

export interface CreateAiChatSessionResponse {
  status: "success" | "error";
  session: AIChatSession | null;
  message: string;
  error: string | null;
}

export interface GetAiChatSessionsResponse {
  status: "success" | "error";
  sessions: AIChatSession[];
  message: string;
  error: string | null;
}

export interface DeleteAiChatSessionResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

export interface SendAiChatMessageResponse {
  status: "success" | "error";
  assistantMessage: AIChatMessage | null;
  message: string;
  error: string | null;
}

export interface GetAiChatMessagesResponse {
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
// 워크스페이스 AI Chat 세션 API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 새 대화(세션) 생성 API (POST /api/workspaces/{workspace_id}/ai-chat/sessions)
 */
export async function createAiChatSessionApi(workspaceId: string): Promise<CreateAiChatSessionResponse> {
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
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/sessions`, {
      method: "POST",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "새 대화를 만들지 못했습니다.";
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
    console.error("createAiChatSessionApi error:", error);
    return {
      status: "error",
      session: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 대화(세션) 목록 조회 API (GET /api/workspaces/{workspace_id}/ai-chat/sessions)
 * - 최근 활동순 정렬, 제목은 첫 질문으로 자동 생성됨
 */
export async function getAiChatSessionsApi(workspaceId: string): Promise<GetAiChatSessionsResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      sessions: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/sessions`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "대화 목록을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";

      return {
        status: "error",
        sessions: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      sessions: data.sessions || [],
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getAiChatSessionsApi error:", error);
    return {
      status: "error",
      sessions: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 대화(세션) 삭제 API (DELETE /api/workspaces/{workspace_id}/ai-chat/sessions/{session_id})
 */
export async function deleteAiChatSessionApi(
  workspaceId: string,
  sessionId: string
): Promise<DeleteAiChatSessionResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/sessions/${sessionId}`,
      { method: "DELETE" }
    );

    let data: any = null;
    try {
      data = await response.json();
    } catch {
      // 본문 없는 응답일 수 있음 - 무시
    }

    if (!response.ok || data?.status === "error") {
      let defaultMsg = "대화 삭제에 실패했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 대화입니다.";

      return {
        status: "error",
        message: data?.message || defaultMsg,
        error: data?.error || `HTTP_${response.status}`,
      };
    }

    return { status: "success", message: "대화가 삭제되었습니다.", error: null };
  } catch (error) {
    console.error("deleteAiChatSessionApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 질문 전송 + AI 답변 생성 API (POST /api/workspaces/{workspace_id}/ai-chat/sessions/{session_id}/messages)
 * - 세션을 자동으로 생성/재사용하지 않으므로, 반드시 사전에 세션이 있어야 한다.
 */
export async function sendAiChatMessageApi(
  workspaceId: string,
  sessionId: string,
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
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/sessions/${sessionId}/messages`,
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
      else if (response.status === 404) defaultMsg = "존재하지 않는 대화입니다.";
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
    console.error("sendAiChatMessageApi error:", error);
    return {
      status: "error",
      assistantMessage: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 5. 대화(세션) 기록 조회 API (GET /api/workspaces/{workspace_id}/ai-chat/sessions/{session_id}/messages)
 */
export async function getAiChatMessagesApi(
  workspaceId: string,
  sessionId: string
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/ai-chat/sessions/${sessionId}/messages`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "대화 기록을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 대화입니다.";

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
 * 6. 특정 AI 답변 메시지의 근거 자료 조회 API (GET /api/workspaces/{workspace_id}/ai-chat/messages/{message_id}/sources)
 * - 세션 구조 개편과 무관하게 경로 그대로 유지됨
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
