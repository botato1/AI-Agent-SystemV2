// src/services/dashboard.ts
import { authFetch } from "./auth";

export interface DashboardSummaryResponse {
  status: "success" | "error";
  total_meeting_count: number;
  member_count: number;
  last_meeting_at: string | null;
  week_meeting_count: number;
  week_duration_ms: number;
  week_contradiction_count: number;
  message?: string;
  error?: string | null;
}

/**
 * 대시보드 요약 통계 조회 API (GET /api/workspaces/{workspace_id}/dashboard/summary)
 */
export async function getDashboardSummaryApi(
  workspaceId: string
): Promise<DashboardSummaryResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      total_meeting_count: 0,
      member_count: 0,
      last_meeting_at: null,
      week_meeting_count: 0,
      week_duration_ms: 0,
      week_contradiction_count: 0,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/dashboard/summary`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "대시보드 요약 통계를 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스입니다.";

      return {
        status: "error",
        total_meeting_count: 0,
        member_count: 0,
        last_meeting_at: null,
        week_meeting_count: 0,
        week_duration_ms: 0,
        week_contradiction_count: 0,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      total_meeting_count: data.total_meeting_count ?? 0,
      member_count: data.member_count ?? 0,
      last_meeting_at: data.last_meeting_at ?? null,
      week_meeting_count: data.week_meeting_count ?? 0,
      week_duration_ms: data.week_duration_ms ?? 0,
      week_contradiction_count: data.week_contradiction_count ?? 0,
    };
  } catch (error) {
    console.error("getDashboardSummaryApi error:", error);
    return {
      status: "error",
      total_meeting_count: 0,
      member_count: 0,
      last_meeting_at: null,
      week_meeting_count: 0,
      week_duration_ms: 0,
      week_contradiction_count: 0,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}