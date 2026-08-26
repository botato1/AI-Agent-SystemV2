import { authFetch } from "./auth";

// --- 타입 정의 ---

export type FileKind = "document" | "audio" | "image" | "code" | string;
export type FileAnalysisStatus = "pending" | "processing" | "completed" | "failed" | string;

export interface RoomFile {
  id: string;
  original_filename: string;
  file_kind: FileKind;
  analysis_status: FileAnalysisStatus;
  created_at: string;
}

export interface LinkRoomFileResponse {
  status: "success" | "error";
  file: RoomFile | null;
  message: string;
  error: string | null;
}

export interface GetRoomFilesResponse {
  status: "success" | "error";
  files: RoomFile[];
  message: string;
  error: string | null;
}

export interface UnlinkRoomFileResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 파일 연결 API (POST /api/workspaces/{workspace_id}/rooms/{room_id}/files)
 */
export async function linkRoomFileApi(
  workspaceId: string,
  roomId: string,
  fileId: string
): Promise<LinkRoomFileResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      file: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/files`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: fileId }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "파일 연결에 실패했습니다.";
      if (data.error === "already_linked" || response.status === 409) {
        defaultMsg = "이미 연결된 파일입니다.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 연결할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "채팅방 또는 파일을 찾을 수 없습니다.";
      }

      return {
        status: "error",
        file: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      file: data.link || data.file || data,
      message: data.message || "파일이 채팅방에 연결되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("linkRoomFileApi error:", error);
    return {
      status: "error",
      file: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 연결된 파일 목록 조회 API (GET /api/workspaces/{workspace_id}/rooms/{room_id}/files)
 */
export async function getRoomFilesApi(workspaceId: string, roomId: string): Promise<GetRoomFilesResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      files: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/files`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "연결된 파일 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 채팅방입니다.";
      }

      return {
        status: "error",
        files: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      files: data.files || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getRoomFilesApi error:", error);
    return {
      status: "error",
      files: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 파일 연결 해제 API (DELETE /api/workspaces/{workspace_id}/rooms/{room_id}/files/{file_id})
 */
export async function unlinkRoomFileApi(
  workspaceId: string,
  roomId: string,
  fileId: string
): Promise<UnlinkRoomFileResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/rooms/${roomId}/files/${fileId}`,
      { method: "DELETE" }
    );

    if (response.status === 204) {
      return {
        status: "success",
        message: "파일 연결이 해제되었습니다.",
        error: null,
      };
    }

    const textData = await response.text();
    const data = textData ? JSON.parse(textData) : {};

    if (!response.ok || data.status === "error") {
      let defaultMsg = "파일 연결 해제에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 해제할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "연결 정보를 찾을 수 없습니다.";
      }

      return {
        status: "error",
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      message: data.message || "파일 연결이 해제되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("unlinkRoomFileApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
