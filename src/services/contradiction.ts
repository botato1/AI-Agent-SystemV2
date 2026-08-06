import { authFetch } from "./auth";

// --- 타입 정의 ---

export type ContradictionSourceType = "meeting_segment" | "room_message";
// "decision"이면 결정 변경 감지(judgment_case로 Case2/3 구분), 그 외는 문서-발화 모순 감지.
export type ContradictionReferenceType = "content_chunk" | "code_fact" | "decision";
export type ContradictionSeverity = "low" | "medium" | "high";
export type ContradictionStatus = "unresolved" | "resolved" | "dismissed";
export type ContradictionResolutionType = "change_acknowledged" | "keep_reference";
export type GenerationStatus = "pending" | "processing" | "completed" | "failed";
// decision 소스 전용 - 근거 있는 변경(Case2)/근거 없는 변경(Case3) 구분.
export type ContradictionJudgmentCase = "reasoned_change" | "unreasoned_change";

export interface ReferenceLocation {
  relative_path?: string;
  symbol_name?: string;
  start_line?: number;
  end_line?: number;
}

export interface Contradiction {
  id: string;
  workspace_id: string;
  category_id: string;
  source_type: ContradictionSourceType;
  meeting_segment_id?: string | null;
  room_message_id?: string | null;
  reference_type: ContradictionReferenceType;
  reference_file_id: string;
  reference_chunk_id?: string | null;
  reference_code_fact_id?: string | null;
  statement_text_snapshot: string;
  reference_text_snapshot: string;
  // 화면에 바로 띄울 수 있는 "기존 자료와 다르다" 비교 문구. 없으면(예전 데이터) statement/reference
  // 스냅샷을 조합해서 프론트에서 직접 구성한다.
  display_message?: string | null;
  reference_source_name?: string | null;
  reference_location?: ReferenceLocation | null;
  reason?: string | null;
  confidence_score: number;
  severity: ContradictionSeverity;
  // 결정 변경의 근거 유무(Case2/3 구분) - reference_type이 "decision"일 때만 의미 있음
  judgment_case?: ContradictionJudgmentCase | null;
  status: ContradictionStatus;
  // 되돌리기 가능 여부 판단용 - 값이 없으면(예전 응답) "유지"로 해결된 것도 판별을 못 하므로
  // 되돌리기 버튼을 우선 보여준다.
  resolution_type?: ContradictionResolutionType | null;
  detected_at: string;
  updated_at: string;
}

export interface ChangeSummaryDraft {
  id: string;
  workspace_id: string;
  contradiction_id: string;
  resolution_id: string;
  context_type: "meeting" | "chat";
  original_reference_text: string;
  accepted_change_text: string;
  generated_summary?: string | null;
  generation_status: GenerationStatus;
  model_name?: string | null;
  created_at: string;
}

export interface GetContradictionListResponse {
  status: "success" | "error";
  contradictions: Contradiction[];
  message: string;
  error: string | null;
}

export interface GetContradictionResponse {
  status: "success" | "error";
  contradiction: Contradiction | null;
  message: string;
  error: string | null;
}

export interface GetChangeSummaryResponse {
  status: "success" | "error";
  changeSummary: ChangeSummaryDraft | null;
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 모순 목록 조회 API (GET /api/workspaces/{workspace_id}/contradictions)
 */
export async function getContradictionListApi(
  workspaceId: string,
  status?: ContradictionStatus
): Promise<GetContradictionListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      contradictions: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const query = status ? `?status=${status}` : "";
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/contradictions${query}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "모순 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      } else if (response.status === 422) {
        defaultMsg = "잘못된 상태 값입니다.";
      }

      return {
        status: "error",
        contradictions: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      contradictions: data.contradictions || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getContradictionListApi error:", error);
    return {
      status: "error",
      contradictions: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 모순 단건 조회 API (GET /api/workspaces/{workspace_id}/contradictions/{contradiction_id})
 */
export async function getContradictionApi(
  workspaceId: string,
  contradictionId: string
): Promise<GetContradictionResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      contradiction: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/contradictions/${contradictionId}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "모순 정보를 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 모순입니다.";
      }

      return {
        status: "error",
        contradiction: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      contradiction: data.contradiction || data,
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getContradictionApi error:", error);
    return {
      status: "error",
      contradiction: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 모순 해결 API (POST /api/workspaces/{workspace_id}/contradictions/{contradiction_id}/resolve)
 *
 * 주의: 실제 응답은 갱신된 모순 객체 하나뿐이다 (resolution/change_summary_draft_id 없음).
 * "이미 처리됨"은 400이 아니라 409로 온다.
 */
export async function resolveContradictionApi(
  workspaceId: string,
  contradictionId: string,
  resolutionType: ContradictionResolutionType,
  note?: string
): Promise<GetContradictionResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      contradiction: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/contradictions/${contradictionId}/resolve`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolution_type: resolutionType, note: note || null }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "모순 해결 처리에 실패했습니다.";
      let errorCode = data.error || `HTTP_${response.status}`;
      if (response.status === 409) {
        defaultMsg = "이미 처리된 모순입니다.";
        errorCode = "already_resolved";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 처리할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 모순입니다.";
      } else if (response.status === 422) {
        defaultMsg = "잘못된 해결 유형입니다.";
      }

      return {
        status: "error",
        contradiction: null,
        message: data.message || data.detail || defaultMsg,
        error: errorCode,
      };
    }

    return {
      status: "success",
      contradiction: data.contradiction || data,
      message: "모순이 해결 처리되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("resolveContradictionApi error:", error);
    return {
      status: "error",
      contradiction: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 모순 무시 API (POST /api/workspaces/{workspace_id}/contradictions/{contradiction_id}/dismiss)
 *
 * 주의: 실제 응답도 갱신된 모순 객체 하나뿐이다. "이미 처리됨"은 409.
 */
export async function dismissContradictionApi(
  workspaceId: string,
  contradictionId: string,
  note?: string
): Promise<GetContradictionResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      contradiction: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/contradictions/${contradictionId}/dismiss`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: note || null }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "모순 무시 처리에 실패했습니다.";
      let errorCode = data.error || `HTTP_${response.status}`;
      if (response.status === 409) {
        defaultMsg = "이미 처리된 모순입니다.";
        errorCode = "already_resolved";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 처리할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 모순입니다.";
      }

      return {
        status: "error",
        contradiction: null,
        message: data.message || data.detail || defaultMsg,
        error: errorCode,
      };
    }

    return {
      status: "success",
      contradiction: data.contradiction || data,
      message: "모순이 무시 처리되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("dismissContradictionApi error:", error);
    return {
      status: "error",
      contradiction: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 5. 모순 되돌리기 API (POST /api/workspaces/{workspace_id}/contradictions/{contradiction_id}/reopen)
 *
 * "유지"(keep_reference)로 해결한 것만 되돌릴 수 있다 - "반영"(change_acknowledged)은 이미
 * 기준문서 변경 요약까지 생성됐을 수 있어서 단순 상태 되돌리기로는 안전하지 않다.
 * resolution_type이 change_acknowledged이거나 이미 unresolved인 항목에 호출하면 409로 거부된다.
 */
export async function reopenContradictionApi(
  workspaceId: string,
  contradictionId: string
): Promise<GetContradictionResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      contradiction: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/contradictions/${contradictionId}/reopen`,
      { method: "POST" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "되돌리기에 실패했습니다.";
      let errorCode = data.error || `HTTP_${response.status}`;
      if (response.status === 409 || response.status === 400) {
        defaultMsg = "'반영'된 항목은 되돌릴 수 없습니다.";
        errorCode = "not_revertible";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 처리할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 모순입니다.";
      }

      return {
        status: "error",
        contradiction: null,
        message: data.message || data.detail || defaultMsg,
        error: errorCode,
      };
    }

    return {
      status: "success",
      contradiction: data.contradiction || data,
      message: "미해결 상태로 되돌렸습니다.",
      error: null,
    };
  } catch (error) {
    console.error("reopenContradictionApi error:", error);
    return {
      status: "error",
      contradiction: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 6. 변경 요약 초안 조회 API
 * (GET /api/workspaces/{workspace_id}/contradictions/{contradiction_id}/change-summary)
 */
export async function getChangeSummaryApi(
  workspaceId: string,
  contradictionId: string
): Promise<GetChangeSummaryResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      changeSummary: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/contradictions/${contradictionId}/change-summary`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "변경 요약 초안을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "변경 요약 초안이 없습니다.";
      }

      return {
        status: "error",
        changeSummary: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      changeSummary: data.change_summary || data,
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getChangeSummaryApi error:", error);
    return {
      status: "error",
      changeSummary: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
