import { authFetch } from "./auth";

// --- 타입 정의 ---

export type WorktreeStatus = "pending" | "processing" | "completed" | "partially_completed" | "failed";
export type FileKind = "document" | "code" | "config" | "image" | "audio" | string;
export type FileAnalysisStatus = "pending" | "processing" | "completed" | "failed" | "excluded" | string;

export interface Worktree {
  id: string;
  workspace_id: string;
  category_id: string;
  root_folder_name: string;
  uploaded_by: string;
  total_file_count: number;
  completed_file_count: number;
  failed_file_count: number;
  excluded_file_count: number;
  status: WorktreeStatus;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorktreeFile {
  id: string;
  original_filename: string;
  relative_path?: string | null;
  file_kind: FileKind;
  analysis_status: FileAnalysisStatus;
  file_size_bytes: number;
  created_at: string;
}

export interface UploadWorktreeResponse {
  status: "success" | "error";
  worktree: Worktree | null;
  message: string;
  error: string | null;
}

export interface GetWorktreeListResponse {
  status: "success" | "error";
  worktrees: Worktree[];
  message: string;
  error: string | null;
}

export interface GetWorktreeResponse {
  status: "success" | "error";
  worktree: Worktree | null;
  message: string;
  error: string | null;
}

export interface GetWorktreeFilesResponse {
  status: "success" | "error";
  files: WorktreeFile[];
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 폴더 업로드(워크트리 생성) API (POST /api/workspaces/{workspace_id}/worktrees)
 *
 * files는 각 File의 filename에 상대 경로(예: backend/main.py)가 포함되어야 하므로,
 * 호출하는 쪽에서 webkitRelativePath 등을 이용해 FormData를 구성해서 넘겨야 한다.
 */
export async function uploadWorktreeApi(
  workspaceId: string,
  rootFolderName: string,
  files: { file: File; relativePath: string }[]
): Promise<UploadWorktreeResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      worktree: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  if (files.length === 0) {
    return {
      status: "error",
      worktree: null,
      message: "업로드할 파일이 없습니다.",
      error: "NO_FILES",
    };
  }

  try {
    const formData = new FormData();
    formData.append("root_folder_name", rootFolderName);
    files.forEach(({ file, relativePath }) => {
      formData.append("files", file, relativePath);
    });

    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/worktrees`, {
      method: "POST",
      body: formData,
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "폴더 업로드에 실패했습니다.";
      if (response.status === 400) {
        defaultMsg = "업로드할 파일이 없습니다.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 업로드할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      } else if (response.status === 422) {
        defaultMsg = "최상위 폴더 이름을 입력해 주세요.";
      }

      return {
        status: "error",
        worktree: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      worktree: data.worktree || data,
      message: data.message || "워크트리 업로드가 접수되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("uploadWorktreeApi error:", error);
    return {
      status: "error",
      worktree: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 워크트리 목록 조회 API (GET /api/workspaces/{workspace_id}/worktrees)
 */
export async function getWorktreeListApi(workspaceId: string): Promise<GetWorktreeListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      worktrees: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/worktrees`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "워크트리 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        worktrees: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      worktrees: data.worktrees || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getWorktreeListApi error:", error);
    return {
      status: "error",
      worktrees: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 워크트리 단건 조회 API (GET /api/workspaces/{workspace_id}/worktrees/{worktree_id})
 */
export async function getWorktreeApi(
  workspaceId: string,
  worktreeId: string
): Promise<GetWorktreeResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      worktree: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/worktrees/${worktreeId}`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "워크트리 정보를 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 워크트리입니다.";
      }

      return {
        status: "error",
        worktree: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      worktree: data.worktree || data,
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getWorktreeApi error:", error);
    return {
      status: "error",
      worktree: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 워크트리 내 파일 목록 조회 API (GET /api/workspaces/{workspace_id}/worktrees/{worktree_id}/files)
 */
export async function getWorktreeFilesApi(
  workspaceId: string,
  worktreeId: string
): Promise<GetWorktreeFilesResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/worktrees/${worktreeId}/files`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "파일 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 워크트리입니다.";
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
    console.error("getWorktreeFilesApi error:", error);
    return {
      status: "error",
      files: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
