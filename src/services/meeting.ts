import { authFetch } from "./auth";

// --- 타입 정의 ---

export type MeetingInputType = "live_recording" | "audio_upload";
export type MeetingStatus =
  | "scheduled"
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
  topic?: string | null;
  input_type: MeetingInputType;
  status: MeetingStatus;
  started_by: string;
  started_at?: string | null;
  scheduled_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  location?: string | null;
  is_online?: boolean | null;
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

export interface MeetingAttendee {
  user_id: string;
  display_name: string;
  is_initial?: boolean;
}

export interface GetMeetingAttendeesResponse {
  status: "success" | "error";
  attendees: MeetingAttendee[];
  message: string;
  error: string | null;
}

export interface UpcomingMeeting {
  id: string;
  title: string;
  topic?: string | null;
  location?: string | null;
  scheduled_at: string;
  attendees: MeetingAttendee[];
}

export interface ScheduleMeetingParams {
  title: string;
  topic?: string | null;
  location?: string | null;
  scheduled_at: string;
  attendee_ids?: string[];
}

export interface ScheduleMeetingResponse {
  status: "success" | "error";
  meeting: Meeting | null;
  message: string;
  error: string | null;
}

export interface GetUpcomingMeetingsResponse {
  status: "success" | "error";
  meetings: UpcomingMeeting[];
  message: string;
  error: string | null;
}

export interface MeetingExportData {
  meeting_id: string;
  title: string;
  location: string | null;
  is_online: boolean | null;
  started_at: string | null;
  attendees: MeetingAttendee[];
  short_summary: string | null;
  filtered_transcript: string | null;
  segments: MeetingSegment[];
}

export interface GetMeetingExportResponse {
  status: "success" | "error";
  data: MeetingExportData | null;
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

export interface RecentMeetingItem {
  id: string;
  title: string;
  started_at: string | null;
  duration_ms: number | null;
  attendee_count: number;
  preview: string | null;
  contradiction_count: number;
}

export interface GetRecentMeetingsResponse {
  status: "success" | "error";
  meetings: RecentMeetingItem[];
  total_count: number;
  message: string;
  error: string | null;
}

export interface SearchMeetingsParams {
  q?: string;
  date_from?: string;
  date_to?: string;
}

export interface SearchMeetingsResponse {
  status: "success" | "error";
  meetings: RecentMeetingItem[];
  total_count: number;
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
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스입니다.";

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
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

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
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 삭제할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

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
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

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
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "아직 요약이 생성되지 않았거나, 존재하지 않는 회의입니다.";

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
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

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
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 회의를 시작할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 연결하려는 채팅방입니다.";
      else if (response.status === 422) defaultMsg = "회의 제목을 입력해 주세요.";

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
      if (response.status === 400) defaultMsg = "실시간 녹음 회의가 아닙니다.";
      else if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 일시정지할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
      else if (response.status === 409) defaultMsg = "녹음 중인 회의가 아닙니다.";

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
      if (response.status === 400) defaultMsg = "실시간 녹음 회의가 아닙니다.";
      else if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 재개할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";
      else if (response.status === 409) defaultMsg = "일시정지 중인 회의가 아닙니다.";

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
 * 12. 회의 제목 변경 API (PATCH /api/workspaces/{workspace_id}/meetings/{meeting_id})
 */
export async function renameMeetingApi(
  workspaceId: string,
  meetingId: string,
  title: string
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 제목 변경에 실패했습니다.";
      if (response.status === 400) defaultMsg = "제목을 1~200자로 입력해 주세요.";
      else if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 변경할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

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
      message: "회의 제목이 변경되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("renameMeetingApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 회의 제목/주제/장소 수정 API (PATCH /api/workspaces/{workspace_id}/meetings/{meeting_id})
 */
export async function updateMeetingInfoApi(
  workspaceId: string,
  meetingId: string,
  info: { title: string; topic?: string | null; location?: string | null }
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
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: info.title,
        topic: info.topic || null,
        location: info.location || null,
      }),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 정보 수정에 실패했습니다.";
      if (response.status === 400) defaultMsg = "제목을 1~200자로 입력해 주세요.";
      else if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 변경할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

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
      message: "회의 정보가 수정되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("updateMeetingInfoApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 13. 화자 이름 매핑 API (PATCH /api/workspaces/{workspace_id}/meetings/{meeting_id}/speakers)
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
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 매핑할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

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

/**
 * 회의 참석자 조회 API (GET /api/workspaces/{workspace_id}/meetings/{meeting_id}/attendees)
 */
export async function getMeetingAttendeesApi(
  workspaceId: string,
  meetingId: string
): Promise<GetMeetingAttendeesResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      attendees: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/attendees`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "참석자 목록을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

      return {
        status: "error",
        attendees: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      attendees: data.attendees || [],
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getMeetingAttendeesApi error:", error);
    return {
      status: "error",
      attendees: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 회의 참석자 지정/수정 API (PATCH /api/workspaces/{workspace_id}/meetings/{meeting_id}/attendees)
 */
export async function setMeetingAttendeesApi(
  workspaceId: string,
  meetingId: string,
  userIds: string[]
): Promise<GetMeetingAttendeesResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      attendees: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/attendees`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_ids: userIds }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "참석자 지정에 실패했습니다.";
      if (response.status === 400) defaultMsg = "워크스페이스 멤버가 아닌 사용자가 포함되어 있습니다.";
      else if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 지정할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

      return {
        status: "error",
        attendees: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      attendees: data.attendees || [],
      message: "참석자가 지정되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("setMeetingAttendeesApi error:", error);
    return {
      status: "error",
      attendees: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 회의 예약 API (POST /api/workspaces/{workspace_id}/meetings/schedule)
 */
export async function scheduleMeetingApi(
  workspaceId: string,
  params: ScheduleMeetingParams
): Promise<ScheduleMeetingResponse> {
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
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/schedule`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: params.title,
        topic: params.topic || null,
        location: params.location || null,
        scheduled_at: params.scheduled_at,
        attendee_ids: params.attendee_ids || [],
      }),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의 예약에 실패했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 회의를 예약할 수 있습니다.";
      else if (response.status === 400) defaultMsg = "참석자 중 워크스페이스 멤버가 아닌 사용자가 있습니다.";
      else if (response.status === 422) defaultMsg = "회의 제목 또는 예정 시각을 확인해 주세요.";

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
      message: "회의가 예약되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("scheduleMeetingApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 예정된 회의 목록 조회 API (GET /api/workspaces/{workspace_id}/meetings/upcoming)
 */
export async function getUpcomingMeetingsApi(workspaceId: string): Promise<GetUpcomingMeetingsResponse> {
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
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/upcoming`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "예정된 회의 목록을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";

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
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getUpcomingMeetingsApi error:", error);
    return {
      status: "error",
      meetings: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 예정된 회의를 실제 녹음으로 전환하는 API (POST /api/workspaces/{workspace_id}/meetings/{meeting_id}/begin)
 */
export async function beginScheduledMeetingApi(
  workspaceId: string,
  meetingId: string
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
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/begin`, {
      method: "POST",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "예정된 회의를 시작하지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 회의를 시작할 수 있습니다.";
      else if (response.status === 409) defaultMsg = "이미 시작되었거나 예정된 회의가 아닙니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 회의입니다.";

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
      message: "회의가 시작되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("beginScheduledMeetingApi error:", error);
    return {
      status: "error",
      meeting: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 회의록 조립용 원본 데이터 조회 API (GET /api/workspaces/{workspace_id}/meetings/{meeting_id}/export)
 */
export async function getMeetingExportApi(
  workspaceId: string,
  meetingId: string
): Promise<GetMeetingExportResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      data: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/export`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의록 데이터를 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스이거나 회의입니다.";

      return {
        status: "error",
        data: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      data,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getMeetingExportApi error:", error);
    return {
      status: "error",
      data: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 최근 회의 목록 조회 API (GET /api/workspaces/{workspace_id}/meetings/recent)
 */
export async function getRecentMeetingsApi(
  workspaceId: string,
  limit: number = 10
): Promise<GetRecentMeetingsResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meetings: [],
      total_count: 0,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/recent?limit=${limit}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "최근 회의 목록을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스입니다.";

      return {
        status: "error",
        meetings: [],
        total_count: 0,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meetings: data.meetings || [],
      total_count: data.total_count ?? 0,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getRecentMeetingsApi error:", error);
    return {
      status: "error",
      meetings: [],
      total_count: 0,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 키워드/의미 기반 회의록 검색 API (GET /api/workspaces/{workspace_id}/meetings/search)
 */
export async function searchMeetingsApi(
  workspaceId: string,
  params: SearchMeetingsParams
): Promise<SearchMeetingsResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      meetings: [],
      total_count: 0,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const queryParams = new URLSearchParams();
    if (params.q) queryParams.append("q", params.q);
    if (params.date_from) queryParams.append("date_from", params.date_from);
    if (params.date_to) queryParams.append("date_to", params.date_to);

    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/search?${queryParams.toString()}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "회의록 검색에 실패했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 검색할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 워크스페이스입니다.";

      return {
        status: "error",
        meetings: [],
        total_count: 0,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      meetings: data.meetings || [],
      total_count: data.total_count ?? 0,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("searchMeetingsApi error:", error);
    return {
      status: "error",
      meetings: [],
      total_count: 0,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}