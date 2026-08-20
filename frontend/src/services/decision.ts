import { authFetch } from "./auth";

// --- 타입 정의 ---

export type DecisionStatus = "active" | "superseded" | "cancelled";

export interface DecisionHistoryEntry {
  value: string;
  reason: string | null;
  decided_at: string;
  status: DecisionStatus;
}

// 워크스페이스 전체 기준 결정사항 - 회의 하나가 아니라 여러 회의를 넘나들며
// 같은 주제가 어떻게 바뀌어왔는지(history)까지 포함해서 내려온다.
export interface WorkspaceDecision {
  id: string;
  workspace_id: string;
  meeting_id: string;
  title: string;
  decision_text: string;
  reason: string | null;
  status: DecisionStatus;
  decided_at: string;
  // 최신 → 과거 순, 현재(active) 버전도 포함되어 있어 이 배열 하나로 타임라인 전체를 그린다
  history: DecisionHistoryEntry[];
}

export interface GetWorkspaceDecisionsResponse {
  status: "success" | "error";
  decisions: WorkspaceDecision[];
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 워크스페이스 결정사항 조회 API (GET /api/workspaces/{workspace_id}/decisions)
 * status 생략 시 백엔드 기본값은 active(현재 유효한 것만)
 */
export async function getWorkspaceDecisionsApi(
  workspaceId: string,
  status?: DecisionStatus
): Promise<GetWorkspaceDecisionsResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      decisions: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const query = status ? `?status=${status}` : "";
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/decisions${query}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "결정사항을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        decisions: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      decisions: data.decisions || [],
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getWorkspaceDecisionsApi error:", error);
    return {
      status: "error",
      decisions: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
