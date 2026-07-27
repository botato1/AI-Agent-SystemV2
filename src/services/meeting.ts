import { authFetch } from "./auth";

// --- 타입 정의 ---

export type MeetingInputType = "live_recording" | "audio_upload";
export type MeetingStatus =
  | "created"
  | "recording"
  | "paused"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";
export type GenerationStatus = "pending" | "processing" | "completed" | "failed";
export type DecisionStatus = "active" | "superseded" | "cancelled";

export interface Meeting {
  id: string;
  workspace_id: string;
  category_id: string;
  related_room_id?: string | null;
  source_file_id?: string | null;
  title: string;
  input_type: MeetingInputType;
  status: MeetingStatus;
  started_by: string;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  created_at: string;
  updated_at: string;
}

export interface MeetingStart extends Meeting {
  ws_ticket: string;
}

export interface MeetingSegment {
  id: string;
  meeting_id: string;
  speaker_label?: string | null;
  speaker_user_id?: string | null;
  content: string;
  start_ms: number;
  end_ms: number;
  segment_index: number;
  is_edited: boolean;
  created_at: string;
  updated_at: string;
}

export interface MeetingSummary {
  id: string;
  meeting_id: string;
  full_summary?: string | null;
  short_summary?: string | null;
  discussion_points?: unknown;
  generation_status: GenerationStatus;
  generated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Decision {
  id: string;
  workspace_id: string;
  meeting_id: string;
  title: string;
  decision_text: string;
  reason?: string | null;
  status: DecisionStatus;
  decided_at: string;
  created_at: string;
  updated_at: string;
}

export interface GetMeetingListResponse {
  status: "success" | "error";
  meetings: Meeting[];
  message: string;
  error: string | null;
}

export interface GetMeetingResponse {
  status: "success" | "error";
  meeting: Meeting | null;
  message: string;
  error: string | null;
}

export interface StartMeetingResponse {
  status: "success" | "error";
  meeting: MeetingStart | null;
  message: string;
  error: string | null;
}

export interface DeleteMeetingResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

export interface GetMeetingSegmentsResponse {
  status: "success" | "error";
  segments: MeetingSegment[];
  message: string;
  error: string | null;
}

export interface GetMeetingSummaryResponse {
  status: "success" | "error";
  summary: MeetingSummary | null;
  message: string;
  error: string | null;
}

export interface GetMeetingDecisionsResponse {
  status: "success" | "error";
  decisions: Decision[];
  message: string;
  error: string | null;
}

export interface MapSpeakerNamesResponse {
  status: "success" | "error";
  meetingId: string | null;
  speakerLabels: Record<string, string>;
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 회의 목록 조회 API (GET /api/workspaces/{workspace_id}/meetings)
 */
export async function getMeetingListApi(workspaceId: string): Promise<GetMeetingListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meetings: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/meetings`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        meetings: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meetings: data.meetings || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getMeetingListApi error:", error);
    return {
      status: "error",
      meetings: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 회의 단건 조회 API (GET /api/workspaces/{workspace_id}/meetings/{meeting_id})
 */
export async function getMeetingApi(workspaceId: string, meetingId: string): Promise<GetMeetingResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meeting: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 정보를 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
      }

      return {
        status: "error",
        meeting: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meeting: data.meeting || data,
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getMeetingApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 회의 삭제 API (DELETE /api/workspaces/{workspace_id}/meetings/{meeting_id})
 */
export async function deleteMeetingApi(
  workspaceId: string,
  meetingId: string
): Promise<DeleteMeetingResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}`,
      { method: "DELETE" }
    );

    if (response.status === 204) {
      return {
        status: "success",
        message: "회의가 삭제되었습니다.",
        error: null,
      };
    }

    const textData = await response.text();
    const data = textData ? JSON.parse(textData) : {};

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 삭제에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 삭제할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
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
    console.error("deleteMeetingApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 발화 세그먼트 목록 조회 API (GET /api/workspaces/{workspace_id}/meetings/{meeting_id}/segments)
 */
export async function getMeetingSegmentsApi(
  workspaceId: string,
  meetingId: string
): Promise<GetMeetingSegmentsResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      segments: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/segments`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "발화 세그먼트를 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
      }

      return {
        status: "error",
        segments: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      segments: data.segments || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getMeetingSegmentsApi error:", error);
    return {
      status: "error",
      segments: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 5. 회의 요약 조회 API (GET /api/workspaces/{workspace_id}/meetings/{meeting_id}/summary)
 */
export async function getMeetingSummaryApi(
  workspaceId: string,
  meetingId: string
): Promise<GetMeetingSummaryResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      summary: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/summary`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 요약을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "아직 요약이 생성되지 않았거나, 존재하지 않는 회의입니다.";
      }

      return {
        status: "error",
        summary: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      summary: data.summary || data,
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getMeetingSummaryApi error:", error);
    return {
      status: "error",
      summary: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 6. 회의 결정사항 목록 조회 API (GET /api/workspaces/{workspace_id}/meetings/{meeting_id}/decisions)
 */
export async function getMeetingDecisionsApi(
  workspaceId: string,
  meetingId: string
): Promise<GetMeetingDecisionsResponse> {
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
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/decisions`,
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
        defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
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
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getMeetingDecisionsApi error:", error);
    return {
      status: "error",
      decisions: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 7. 회의 음성 파일 업로드 API (POST /api/workspaces/{workspace_id}/meetings/upload, multipart/form-data)
 */
export async function uploadMeetingAudioApi(
  workspaceId: string,
  file: File,
  title: string,
  relatedRoomId?: string
): Promise<GetMeetingResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meeting: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", title);
    if (relatedRoomId) {
      formData.append("related_room_id", relatedRoomId);
    }

    // multipart/form-data는 브라우저가 boundary를 포함해 Content-Type을 자동 설정해야 하므로
    // 여기서 직접 헤더를 지정하지 않는다.
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/upload`,
      {
        method: "POST",
        body: formData,
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "음성 파일 업로드에 실패했습니다.";
      if (data.error === "unsupported_file_type" || response.status === 400) {
        defaultMsg = "지원하지 않는 음성 파일 형식입니다. (mp3/wav/m4a/webm)";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 업로드할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 연결하려는 채팅방입니다.";
      } else if (response.status === 422) {
        defaultMsg = "회의 제목을 입력해 주세요.";
      }

      return {
        status: "error",
        meeting: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meeting: data.meeting || data,
      message: data.message || "회의 음성 업로드가 접수되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("uploadMeetingAudioApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 8. 실시간 녹음 시작 API (POST /api/workspaces/{workspace_id}/meetings/start)
 * 실시간 녹음(웹소켓 스트리밍) 기능 구현 시 사용 — 현재 단계에선 UI 미연결
 */
export async function startMeetingApi(
  workspaceId: string,
  title: string,
  relatedRoomId?: string
): Promise<StartMeetingResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meeting: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/start`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title, related_room_id: relatedRoomId || null }),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 녹음 시작에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 회의를 시작할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 연결하려는 채팅방입니다.";
      } else if (response.status === 422) {
        defaultMsg = "회의 제목을 입력해 주세요.";
      }

      return {
        status: "error",
        meeting: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meeting: data.meeting || data,
      message: data.message || "회의 녹음이 시작되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("startMeetingApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 9. 실시간 녹음 종료 API (POST /api/workspaces/{workspace_id}/meetings/{meeting_id}/end)
 * 실시간 녹음 기능 구현 시 사용 — 현재 단계에선 UI 미연결
 */
export async function endMeetingApi(
  workspaceId: string,
  meetingId: string
): Promise<GetMeetingResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meeting: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/end`,
      { method: "POST" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 녹음 종료에 실패했습니다.";
      if (data.error === "not_recording" || response.status === 400) {
        defaultMsg = "이미 종료됐거나 녹음 중인 회의가 아닙니다.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 종료할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
      }

      return {
        status: "error",
        meeting: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meeting: data.meeting || data,
      message: data.message || "회의 녹음이 종료되었습니다. STT 처리가 시작됩니다.",
      error: null,
    };
  } catch (error) {
    console.error("endMeetingApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 10. 실시간 녹음 일시정지 API (POST /api/workspaces/{workspace_id}/meetings/{meeting_id}/pause)
 * 실시간 녹음 기능 구현 시 사용 — 현재 단계에선 UI 미연결
 */
export async function pauseMeetingApi(
  workspaceId: string,
  meetingId: string
): Promise<GetMeetingResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meeting: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/pause`,
      { method: "POST" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 일시정지에 실패했습니다.";
      if (response.status === 400) {
        defaultMsg = "실시간 녹음 회의가 아닙니다.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 일시정지할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
      } else if (response.status === 409) {
        defaultMsg = "녹음 중인 회의가 아닙니다.";
      }

      return {
        status: "error",
        meeting: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meeting: data.meeting || data,
      message: data.message || "회의가 일시정지되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("pauseMeetingApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 11. 실시간 녹음 재개 API (POST /api/workspaces/{workspace_id}/meetings/{meeting_id}/resume)
 * 실시간 녹음 기능 구현 시 사용 — 현재 단계에선 UI 미연결
 */
export async function resumeMeetingApi(
  workspaceId: string,
  meetingId: string
): Promise<GetMeetingResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meeting: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/resume`,
      { method: "POST" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 재개에 실패했습니다.";
      if (response.status === 400) {
        defaultMsg = "실시간 녹음 회의가 아닙니다.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 재개할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
      } else if (response.status === 409) {
        defaultMsg = "일시정지 중인 회의가 아닙니다.";
      }

      return {
        status: "error",
        meeting: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meeting: data.meeting || data,
      message: data.message || "회의가 재개되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("resumeMeetingApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 12. 화자 이름 매핑 API (PATCH /api/workspaces/{workspace_id}/meetings/{meeting_id}/speakers)
 *
 * STT 원본 화자 라벨(SPEAKER_00 등)을 실명으로 매핑한다. 저장된 발화도 즉시 소급 변경되고
 * (되돌릴 수 없음), 이후 실시간 발화에도 계속 적용된다. 여러 번 호출해도 기존 매핑은 유지된 채
 * 새 매핑만 누적된다.
 */
export async function mapSpeakerNamesApi(
  workspaceId: string,
  meetingId: string,
  mapping: Record<string, string>
): Promise<MapSpeakerNamesResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meetingId: null,
      speakerLabels: {},
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/speakers`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mapping }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "화자 이름 매핑에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 매핑할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
      }

      return {
        status: "error",
        meetingId: null,
        speakerLabels: {},
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meetingId: data.meeting_id ?? meetingId,
      speakerLabels: data.speaker_labels || {},
      message: data.message || "화자 이름이 매핑되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("mapSpeakerNamesApi error:", error);
    return {
      status: "error",
      meetingId: null,
      speakerLabels: {},
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
