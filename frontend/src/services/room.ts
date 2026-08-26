import { authFetch } from "./auth";

// --- 타입 정의 ---

export interface Room {
  id: string;
  workspace_id: string;
  name: string;
  created_by?: string;
  created_at?: string;
  category_id?: string | null;
}

export interface GetRoomListResponse {
  status: "success" | "error";
  rooms: Room[];
  message: string;
  error: string | null;
}

export interface GetRoomResponse {
  status: "success" | "error";
  room: Room | null;
  message: string;
  error: string | null;
}

export interface CreateRoomResponse {
  status: "success" | "error";
  room: Room | null;
  message: string;
  error: string | null;
}

export interface UpdateRoomResponse {
  status: "success" | "error";
  room: Room | null;
  message: string;
  error: string | null;
}

export interface DeleteRoomResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 채팅방 목록 조회 API (GET /api/workspaces/{workspace_id}/rooms)
 */
export async function getRoomListApi(workspaceId: string, categoryId?: string): Promise<GetRoomListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      rooms: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const query = categoryId ? `?category_id=${categoryId}` : "";
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/rooms${query}`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "채팅방 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        rooms: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      rooms: data.rooms || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getRoomListApi error:", error);
    return {
      status: "error",
      rooms: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 채팅방 생성 API (POST /api/workspaces/{workspace_id}/rooms)
 */
export async function createRoomApi(
  workspaceId: string,
  name: string,
  categoryId?: string
): Promise<CreateRoomResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      room: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/rooms`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(categoryId ? { name, category_id: categoryId } : { name }),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "채팅방 생성에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 채팅방을 생성할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      } else if (response.status === 422) {
        defaultMsg = "채팅방 이름은 1~100자로 입력해 주세요.";
      }

      return {
        status: "error",
        room: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      room: data.room || data,
      message: data.message || "채팅방이 생성되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("createRoomApi error:", error);
    return {
      status: "error",
      room: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 채팅방 이름 수정 API (PATCH /api/workspaces/{workspace_id}/rooms/{room_id})
 */
export async function updateRoomApi(
  workspaceId: string,
  roomId: string,
  updates: { name?: string; category_id?: string }
): Promise<UpdateRoomResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      room: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(updates),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "채팅방 이름 수정에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 수정할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 채팅방입니다.";
      } else if (response.status === 422) {
        defaultMsg = "채팅방 이름은 1~100자로 입력해 주세요.";
      }

      return {
        status: "error",
        room: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      room: data.room || data,
      message: data.message || "수정 완료",
      error: null,
    };
  } catch (error) {
    console.error("updateRoomApi error:", error);
    return {
      status: "error",
      room: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 5. 채팅방 삭제 API (DELETE /api/workspaces/{workspace_id}/rooms/{room_id})
 */
export async function deleteRoomApi(workspaceId: string, roomId: string): Promise<DeleteRoomResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}`,
      {
        method: "DELETE",
      }
    );

    if (response.status === 204) {
      return {
        status: "success",
        message: "채팅방이 삭제되었습니다.",
        error: null,
      };
    }

    const textData = await response.text();
    const data = textData ? JSON.parse(textData) : {};

    if (!response.ok || data.status === "error") {
      let defaultMsg = "채팅방 삭제에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 삭제할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 채팅방입니다.";
      }

      return {
        status: "error",
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      message: data.message || "삭제 성공",
      error: null,
    };
  } catch (error) {
    console.error("deleteRoomApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
