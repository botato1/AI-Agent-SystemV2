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

export interface DocumentGraphNode {
  file_id: string;
  filename: string;
}

export interface DocumentGraphEdge {
  source_file_id: string;
  target_file_id: string;
  similarity_score: number;
}

export interface GetDocumentGraphResponse {
  status: "success" | "error";
  nodes: DocumentGraphNode[];
  edges: DocumentGraphEdge[];
  message: string;
  error: string | null;
}

export interface GetDocumentFileResponse {
  status: "success" | "error";
  blob: Blob | null;
  filename: string;
  contentType: string;
  message: string;
  error: string | null;
}

// =============================================================================
// Re:Call: document_figures (표/차트/다이어그램 크롭 이미지)
// =============================================================================

export type DocumentFigureType = "table" | "chart" | "image" | "diagram";

export interface DocumentFigure {
  figure_id: string;
  page_number: number;
  type: DocumentFigureType;
  image_url: string;
}

export interface GetDocumentFiguresResponse {
  status: "success" | "error";
  figures: DocumentFigure[];
  message: string;
  error: string | null;
}

// image_url이 절대 URL(문서 처리 서버 origin)로 오는 경우와, 상대 경로로 오는 경우를 모두 지원
export function resolveFigureUrl(imageUrl: string): string {
  if (/^https?:\/\//i.test(imageUrl)) return imageUrl;
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  return `${API_BASE_URL}${imageUrl}`;
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

/**
 * 6. 문서 유사도 그래프 조회 API (GET /api/workspaces/{workspace_id}/documents/graph)
 *
 * nodes: file_kind=document, analysis_status=completed, is_latest=true 인 파일 전부 포함
 * (고립 노드도 포함). edges: min_score 이상인 유사도 쌍만 포함.
 */
export async function getDocumentGraphApi(
  workspaceId: string,
  minScore: number = 0.5
): Promise<GetDocumentGraphResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      nodes: [],
      edges: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/documents/graph?min_score=${minScore}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "문서 유사도 그래프를 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        nodes: [],
        edges: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      nodes: data.nodes || [],
      edges: data.edges || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getDocumentGraphApi error:", error);
    return {
      status: "error",
      nodes: [],
      edges: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 7. 문서 표/차트/다이어그램 이미지 목록 조회 API (GET /api/workspaces/{workspace_id}/documents/{document_id}/figures)
 */
export async function getDocumentFiguresApi(
  workspaceId: string,
  documentId: string
): Promise<GetDocumentFiguresResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      figures: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/documents/${documentId}/figures`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok) {
      let defaultMsg = "이미지 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 문서입니다.";
      }

      return {
        status: "error",
        figures: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      figures: data.figures || [],
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getDocumentFiguresApi error:", error);
    return {
      status: "error",
      figures: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 8. 원본 파일 바이너리 스트리밍 API (GET /api/workspaces/{workspace_id}/documents/{document_id}/file)
 */
export async function getDocumentFileApi(
  workspaceId: string,
  documentId: string
): Promise<GetDocumentFileResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      blob: null,
      filename: "",
      contentType: "",
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/documents/${documentId}/file`,
      { method: "GET" }
    );

    if (!response.ok) {
      let defaultMsg = "원본 파일을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 403) defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      else if (response.status === 404) defaultMsg = "실제 원본 파일이 디스크에 존재하지 않습니다.";

      return {
        status: "error",
        blob: null,
        filename: "",
        contentType: "",
        message: defaultMsg,
        error: `HTTP_${response.status}`,
      };
    }

    const contentType = response.headers.get("Content-Type") || "application/octet-stream";
    const disposition = response.headers.get("Content-Disposition") || "";
    
    // 파일명 추출 (filename*=utf-8''...)
    let filename = "original_file";
    const filenameMatch = disposition.match(/filename\*=utf-8''([^;]+)/i) || disposition.match(/filename="?([^";]+)"?/i);
    if (filenameMatch && filenameMatch[1]) {
      filename = decodeURIComponent(filenameMatch[1]);
    }

    const blob = await response.blob();

    return {
      status: "success",
      blob,
      filename,
      contentType,
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getDocumentFileApi error:", error);
    return {
      status: "error",
      blob: null,
      filename: "",
      contentType: "",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}