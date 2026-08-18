import { authFetch } from "./auth";

// --- 타입 정의 ---

export type RoomMessageType =
  | "text"
  | "file"
  | "ai_summary"
  | "contradiction_alert"
  | "meeting_notice"
  | "system";

export interface RoomMessage {
  id: string;
  room_id: string;
  sender_user_id: string | null;
  message_type: RoomMessageType;
  content: string;
  reply_to_id?: string | null;
  is_edited: boolean;
  edited_at?: string | null;
  created_at: string;
}

export interface GetRoomMessageListResponse {
  status: "success" | "error";
  messages: RoomMessage[];
  message: string;
  error: string | null;
}

export interface SendRoomMessageResponse {
  status: "success" | "error";
  messageData: RoomMessage | null;
  message: string;
  error: string | null;
}

export interface DeleteRoomMessageResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 채팅방 메시지 목록 조회 API (GET /api/workspaces/{workspace_id}/rooms/{room_id}/messages)
 */
export async function getRoomMessagesApi(
  workspaceId: string,
  roomId: string,
  limit?: number
): Promise<GetRoomMessageListResponse> {
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
    const query = limit ? `?limit=${limit}` : "";
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/messages${query}`,
      {
        method: "GET",
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "메시지 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 채팅방입니다.";
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
    console.error("getRoomMessagesApi error:", error);
    return {
      status: "error",
      messages: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 메시지 전송 API (POST /api/workspaces/{workspace_id}/rooms/{room_id}/messages)
 */
export async function sendRoomMessageApi(
  workspaceId: string,
  roomId: string,
  content: string
): Promise<SendRoomMessageResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      messageData: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/messages`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ content }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "메시지 전송에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 메시지를 보낼 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 채팅방입니다.";
      } else if (response.status === 422) {
        defaultMsg = "메시지 내용을 입력해 주세요.";
      }

      return {
        status: "error",
        messageData: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      messageData: data.message_data || data,
      message: data.message || "메시지가 전송되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("sendRoomMessageApi error:", error);
    return {
      status: "error",
      messageData: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 실시간 수신용 WebSocket 티켓 발급 API (GET /api/workspaces/{workspace_id}/rooms/{room_id}/stream/ticket)
 * 1회용 티켓이라 WebSocket 연결 직전에 매번 새로 발급받아야 함
 */
export interface GetRoomStreamTicketResponse {
  status: "success" | "error";
  wsTicket: string | null;
  message: string;
  error: string | null;
}

export async function getRoomStreamTicketApi(
  workspaceId: string,
  roomId: string
): Promise<GetRoomStreamTicketResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      wsTicket: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/stream/ticket`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok) {
      let defaultMsg = "실시간 연결 티켓 발급에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 채팅방입니다.";
      }

      return {
        status: "error",
        wsTicket: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      wsTicket: data.ws_ticket,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getRoomStreamTicketApi error:", error);
    return {
      status: "error",
      wsTicket: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 메시지 삭제 API (DELETE /api/workspaces/{workspace_id}/rooms/{room_id}/messages/{message_id})
 */
export async function deleteRoomMessageApi(
  workspaceId: string,
  roomId: string,
  messageId: string
): Promise<DeleteRoomMessageResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/messages/${messageId}`,
      {
        method: "DELETE",
      }
    );

    if (response.status === 204) {
      return {
        status: "success",
        message: "메시지가 삭제되었습니다.",
        error: null,
      };
    }

    const textData = await response.text();
    const data = textData ? JSON.parse(textData) : {};

    if (!response.ok || data.status === "error") {
      let defaultMsg = "메시지 삭제에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 삭제할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "채팅방 또는 메시지를 찾을 수 없습니다.";
      }

      return {
        status: "error",
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      message: data.message || "메시지가 삭제되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("deleteRoomMessageApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
