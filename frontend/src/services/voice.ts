import { authFetch } from "./auth";

// --- 타입 정의 ---

export interface VoiceScriptResponse {
  script: string;
}

export interface VoiceProfileStatus {
  registered: boolean;
  registered_at: string | null;
  speaker_name: string | null;
  name_extraction_failed: boolean;
  detected_text: string | null;
}

export interface VoiceProfileResponse {
  status: "success" | "error";
  data: VoiceProfileStatus | null;
  message: string;
  error: string | null;
}

export interface VoiceScriptFetchResponse {
  status: "success" | "error";
  script: string | null;
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 목소리 등록용 문장 조회 (GET /api/auth/voice-profile/script)
 * - 인증 불필요
 */
export async function getVoiceScriptApi(): Promise<VoiceScriptFetchResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/voice-profile/script`, {
      method: "GET",
    });

    const data: VoiceScriptResponse = await response.json();

    if (!response.ok) {
      return {
        status: "error",
        script: null,
        message: response.status === 502 ? "음성 서버 응답에 실패했습니다." : "문장을 불러오지 못했습니다.",
        error: `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      script: data.script,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getVoiceScriptApi error:", error);
    return {
      status: "error",
      script: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 목소리 등록 상태 조회 (GET /api/auth/voice-profile)
 */
export async function getVoiceProfileStatusApi(): Promise<VoiceProfileResponse> {
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
    const response = await authFetch(`${API_BASE_URL}/api/auth/voice-profile`, {
      method: "GET",
    });

    const data: VoiceProfileStatus = await response.json();

    if (!response.ok) {
      return {
        status: "error",
        data: null,
        message: response.status === 401 ? "인증이 만료되었습니다." : "목소리 프로필 상태 조회 실패",
        error: `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      data,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getVoiceProfileStatusApi error:", error);
    return {
      status: "error",
      data: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 목소리 등록 (POST /api/auth/voice-profile)
 * - pcmData: raw PCM16LE 16kHz mono 바이너리 버퍼 (ArrayBuffer 또는 Uint8Array)
 * - speakerName: 이름 추출 실패 시 재요청할 때 사용하는 강제 지정 이름 (선택)
 */
export async function registerVoiceProfileApi(
  pcmData: ArrayBuffer | Uint8Array,
  speakerName?: string
): Promise<VoiceProfileResponse> {
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
    // 쿼리 파라미터 (speaker_name 지정 시)
    const queryParams = new URLSearchParams();
    if (speakerName) {
      queryParams.append("speaker_name", speakerName);
    }
    const queryString = queryParams.toString() ? `?${queryParams.toString()}` : "";

    const bufferData = (pcmData instanceof Uint8Array ? pcmData.buffer : pcmData) as ArrayBuffer;
    const bodyData = new Blob([bufferData], { type: "application/octet-stream" });

    const response = await authFetch(`${API_BASE_URL}/api/auth/voice-profile${queryString}`, {
    method: "POST",
    headers: {
        "Content-Type": "application/octet-stream",
    },
    body: bodyData, 
    });

    const data: VoiceProfileStatus = await response.json();

    if (!response.ok) {
      let defaultMsg = "목소리 등록에 실패했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 404) defaultMsg = "사용자를 찾을 수 없습니다.";
      else if (response.status === 409) defaultMsg = "이미 등록된 목소리가 존재합니다. 기존 목소리를 삭제 후 시도해 주세요.";
      else if (response.status === 502) defaultMsg = "음성 서버 등록 처리 중 오류가 발생했습니다.";

      return {
        status: "error",
        data: null,
        message: defaultMsg,
        error: `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      data,
      message: data.registered ? "목소리가 성공적으로 등록되었습니다." : "이름 추출에 실패했습니다.",
      error: null,
    };
  } catch (error) {
    console.error("registerVoiceProfileApi error:", error);
    return {
      status: "error",
      data: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 목소리 이름 수정 (PATCH /api/auth/voice-profile/rename)
 */
export async function renameVoiceProfileApi(newName: string): Promise<VoiceProfileResponse> {
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
    const queryParams = new URLSearchParams({ new_name: newName });

    const response = await authFetch(`${API_BASE_URL}/api/auth/voice-profile/rename?${queryParams.toString()}`, {
      method: "PATCH",
    });

    const data: VoiceProfileStatus = await response.json();

    if (!response.ok) {
      let defaultMsg = "이름 변경에 실패했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다.";
      else if (response.status === 404) defaultMsg = "등록된 목소리가 없습니다.";
      else if (response.status === 502) defaultMsg = "음성 서버 이름 변경 처리에 실패했습니다.";

      return {
        status: "error",
        data: null,
        message: defaultMsg,
        error: `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      data,
      message: "목소리 이름이 수정되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("renameVoiceProfileApi error:", error);
    return {
      status: "error",
      data: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 5. 목소리 등록 삭제 (DELETE /api/auth/voice-profile)
 */
export async function deleteVoiceProfileApi(): Promise<VoiceProfileResponse> {
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
    const response = await authFetch(`${API_BASE_URL}/api/auth/voice-profile`, {
      method: "DELETE",
    });

    const data: VoiceProfileStatus = await response.json();

    if (!response.ok) {
      return {
        status: "error",
        data: null,
        message: response.status === 401 ? "인증이 만료되었습니다." : "목소리 삭제 실패",
        error: `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      data,
      message: "목소리 등록이 삭제되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("deleteVoiceProfileApi error:", error);
    return {
      status: "error",
      data: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 6. STT 서버에 등록된 전체 화자 이름 목록 조회 (GET /api/auth/voice-profile/list)
 * - 회의 시작 화면에서 참석자 중 누가 목소리를 등록해뒀는지 표시하는 데 사용
 */
export interface VoiceProfileListResponse {
  status: "success" | "error";
  names: string[];
  message: string;
  error: string | null;
}

export async function getVoiceProfileListApi(): Promise<VoiceProfileListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      names: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/auth/voice-profile/list`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok) {
      let defaultMsg = "등록된 목소리 목록을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 502) defaultMsg = "음성 서버와 통신에 실패했습니다.";

      return {
        status: "error",
        names: [],
        message: defaultMsg,
        error: `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      names: data.names || [],
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getVoiceProfileListApi error:", error);
    return {
      status: "error",
      names: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}