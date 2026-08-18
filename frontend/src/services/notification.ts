import { authFetch } from "./auth";

// --- 타입 정의 ---

export type NotificationType =
  | "decision_reminder"
  | "repeat_discussion"
  | "document_recommendation"
  | "contradiction_detected"
  | "contradiction_resolved"
  | "meeting_summary_ready"
  | "file_analysis_completed"
  | "file_analysis_failed";

export type NotificationRefType = "meeting_segment" | "room_message" | "contradiction" | "meeting";

export interface AppNotification {
  id: string;
  user_id: string;
  workspace_id: string;
  type: NotificationType;
  title: string;
  message: string;
  ref_type: NotificationRefType | null;
  ref_id: string | null;
  room_id: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface GetNotificationListResponse {
  status: "success" | "error";
  notifications: AppNotification[];
  message: string;
  error: string | null;
}

export interface MarkNotificationReadResponse {
  status: "success" | "error";
  notification: AppNotification | null;
  message: string;
  error: string | null;
}

// 알림 종류별 켜기/끄기 설정. 한 번도 바꾼 적 없는 사용자는 서버가 전부 true로 내려줌.
export interface NotificationPreferences {
  new_message: boolean;
  meeting_summary: boolean;
  contradiction: boolean;
}

export interface GetNotificationPreferencesResponse {
  status: "success" | "error";
  preferences: NotificationPreferences | null;
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 알림 목록 조회 API (GET /api/workspaces/{workspace_id}/notifications)
 */
export async function getNotificationListApi(
  workspaceId: string,
  unreadOnly?: boolean
): Promise<GetNotificationListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      notifications: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const query = unreadOnly ? "?unread_only=true" : "";
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/notifications${query}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "알림 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        notifications: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      notifications: data.notifications || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getNotificationListApi error:", error);
    return {
      status: "error",
      notifications: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 알림 읽음 처리 API (PATCH /api/workspaces/{workspace_id}/notifications/{notification_id}/read)
 */
export async function markNotificationReadApi(
  workspaceId: string,
  notificationId: string
): Promise<MarkNotificationReadResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      notification: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/notifications/${notificationId}/read`,
      { method: "PATCH" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "알림 읽음 처리에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 처리할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 알림입니다.";
      }

      return {
        status: "error",
        notification: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      notification: data.notification || data,
      message: "알림을 읽음 처리했습니다.",
      error: null,
    };
  } catch (error) {
    console.error("markNotificationReadApi error:", error);
    return {
      status: "error",
      notification: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 알림 설정 조회 API (GET /api/workspaces/{workspace_id}/notification-preferences)
 */
export async function getNotificationPreferencesApi(
  workspaceId: string
): Promise<GetNotificationPreferencesResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      preferences: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/notification-preferences`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "알림 설정을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        preferences: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      preferences: data.preferences || data,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getNotificationPreferencesApi error:", error);
    return {
      status: "error",
      preferences: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 알림 설정 변경 API (PATCH /api/workspaces/{workspace_id}/notification-preferences)
 *
 * 바꾸고 싶은 필드만 전달하면 되고, 응답은 변경 후 전체 설정 상태.
 */
export async function updateNotificationPreferencesApi(
  workspaceId: string,
  patch: Partial<NotificationPreferences>
): Promise<GetNotificationPreferencesResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      preferences: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/notification-preferences`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "알림 설정 변경에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 변경할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        preferences: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      preferences: data.preferences || data,
      message: "알림 설정이 변경되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("updateNotificationPreferencesApi error:", error);
    return {
      status: "error",
      preferences: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
