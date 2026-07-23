import { authFetch } from "./auth";

// --- 타입 정의 ---

export type DocumentAnalysisApiStatus = "pending" | "processing" | "completed" | "failed";

export interface DocumentListItem {
  document_id: string;
  filename: string;
  analysis_status: DocumentAnalysisApiStatus;
  created_at: string;
}

export interface DocumentChunk {
  chunk_index: number;
  content: string;
  page_number?: number | null;
}

export interface DocumentDetail {
  document_id: string;
  workspace_id: string;
  filename: string;
  file_kind: string;
  analysis_status: DocumentAnalysisApiStatus;
  created_at: string;
  raw: {
    original_text: string | null;
    chunks: DocumentChunk[];
  };
  analysis: {
    summary: string | null;
    page_count: number | null;
    table_count: number | null;
    graph_count: number | null;
    ocr_avg_confidence: number | null;
  };
}

export interface GetDocumentListResponse {
  status: "success" | "error";
  documents: DocumentListItem[];
  message: string;
  error: string | null;
}

export interface UploadDocumentResponse {
  status: "success" | "error";
  documentId: string | null;
  filename: string;
  linkStatus: string | null;
  summary: string | null;
  message: string;
  error: string | null;
}

export interface GetDocumentResponse {
  status: "success" | "error";
  document: DocumentDetail | null;
  message: string;
  error: string | null;
}

export interface DeleteDocumentResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

export interface RetryDocumentResponse {
  status: "success" | "error";
  summary: string | null;
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 업로드 문서 목록 조회 API (GET /api/workspaces/{workspace_id}/documents)
 */
export async function getDocumentListApi(workspaceId: string): Promise<GetDocumentListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      documents: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/documents`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "문서 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        documents: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      documents: data.documents || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getDocumentListApi error:", error);
    return {
      status: "error",
      documents: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 문서 업로드 API (POST /api/workspaces/{workspace_id}/documents/upload)
 *
 * 주의: 8003 문서 처리 서버를 동기 호출하므로 응답이 오기까지 최대 5분 정도 걸릴 수 있다.
 * roomId를 넘기면 백엔드가 업로드와 동시에 해당 채팅방에도 자동으로 연결한다.
 */
export async function uploadDocumentApi(
  workspaceId: string,
  file: File,
  roomId?: string,
  documentType: "document" | "meeting" = "document"
): Promise<UploadDocumentResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      documentId: null,
      filename: file.name,
      linkStatus: null,
      summary: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("type", documentType);
    if (roomId) {
      formData.append("room_id", roomId);
    }

    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/documents/upload`, {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "문서 업로드에 실패했습니다.";
      if (data.error === "unsupported_file_type" || data.error === "unsupported_document_type") {
        defaultMsg = "지원하지 않는 파일 형식입니다. (pdf/hwpx/png/jpg/jpeg)";
      } else if (data.error === "use_stt_upload_api") {
        defaultMsg = "음성 파일은 회의 업로드 기능을 이용해 주세요.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 업로드할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 채팅방입니다.";
      } else if (response.status === 502) {
        defaultMsg = "문서 처리 서버 연결에 실패했습니다.";
      }

      return {
        status: "error",
        documentId: null,
        filename: file.name,
        linkStatus: null,
        summary: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      documentId: data.document_id,
      filename: data.filename || file.name,
      linkStatus: data.link_status,
      summary: data.summary,
      message: data.message || "문서 업로드가 완료되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("uploadDocumentApi error:", error);
    return {
      status: "error",
      documentId: null,
      filename: file.name,
      linkStatus: null,
      summary: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 문서 상세 조회 API (GET /api/workspaces/{workspace_id}/documents/{document_id})
 */
export async function getDocumentApi(
  workspaceId: string,
  documentId: string
): Promise<GetDocumentResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      document: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/documents/${documentId}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "문서 상세 정보를 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 문서입니다.";
      }

      return {
        status: "error",
        document: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      document: data.document || null,
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getDocumentApi error:", error);
    return {
      status: "error",
      document: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 문서 삭제 API (DELETE /api/workspaces/{workspace_id}/documents/{document_id})
 */
export async function deleteDocumentApi(
  workspaceId: string,
  documentId: string
): Promise<DeleteDocumentResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/documents/${documentId}`,
      { method: "DELETE" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "문서 삭제에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 삭제할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 문서입니다.";
      }

      return {
        status: "error",
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      message: data.message || "문서 삭제가 완료되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("deleteDocumentApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 5. 문서 재분석 요청 API (POST /api/workspaces/{workspace_id}/documents/{document_id}/retry)
 *
 * 주의: 실제 응답엔 문서에 있는 analysis_status/retry_count 필드가 없다 (성공 시 summary만 옴).
 */
export async function retryDocumentApi(
  workspaceId: string,
  documentId: string
): Promise<RetryDocumentResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/documents/${documentId}/retry`,
      { method: "POST" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "문서 재분석 요청에 실패했습니다.";
      if (data.error === "not_failed" || response.status === 400) {
        defaultMsg = "실패한 문서만 재분석할 수 있습니다.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 요청할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 문서입니다.";
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
      summary: data.summary ?? null,
      message: data.message || "재분석이 완료되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("retryDocumentApi error:", error);
    return {
      status: "error",
      summary: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
