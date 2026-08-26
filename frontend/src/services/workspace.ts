import { authFetch } from "./auth";

// --- 타입 정의 ---

export interface Workspace {
  id: string;
  name: string;
  owner_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface WorkspaceMemberInfo {
  id?: string;
  user_id: string;
  username: string;
  display_name?: string;
  profile_image_url?: string | null;
  role: "owner" | "member";
  joined_at?: string;
}

export interface GetWorkspaceListResponse {
  status: "success" | "error";
  workspaces: Workspace[];
  message: string;
  error: string | null;
}

export interface CreateWorkspaceResponse {
  status: "success" | "error";
  workspace: Workspace | null;
  message: string;
  error: string | null;
}

export interface UpdateWorkspaceResponse {
  status: "success" | "error";
  workspace: Workspace | null;
  message: string;
  error: string | null;
}

export interface DeleteWorkspaceResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

export interface GetWorkspaceMembersResponse {
  status: "success" | "error";
  members: WorkspaceMemberInfo[];
  message: string;
  error: string | null;
}

// result: "added"면 이미 가입된 사용자가 즉시 멤버로 추가된 것(member에 정보 있음),
// "invited"면 미가입 이메일로 초대 메일이 발송된 것(회원가입 링크, 7일 유효, member는 없음)
export interface InviteWorkspaceMemberResponse {
  status: "success" | "error";
  result: "added" | "invited" | null;
  member: WorkspaceMemberInfo | null;
  email: string | null;
  message: string;
  error: string | null;
}

export interface UpdateMemberRoleResponse {
  status: "success" | "error";
  member: WorkspaceMemberInfo | null;
  message: string;
  error: string | null;
}

export interface DeleteWorkspaceMemberResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 내 워크스페이스 목록 조회 API (GET /api/workspaces)
 */
export async function getWorkspaceListApi(): Promise<GetWorkspaceListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      workspaces: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "워크스페이스 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      }

      return {
        status: "error",
        workspaces: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      workspaces: data.workspaces || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getWorkspaceListApi error:", error);
    return {
      status: "error",
      workspaces: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 워크스페이스 생성 API (POST /api/workspaces)
 */
export async function createWorkspaceApi(
  name: string
): Promise<CreateWorkspaceResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      workspace: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name }),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "워크스페이스 생성에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      }

      return {
        status: "error",
        workspace: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      workspace: data.workspace || data,
      message: data.message || "생성 완료",
      error: null,
    };
  } catch (error) {
    console.error("createWorkspaceApi error:", error);
    return {
      status: "error",
      workspace: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 워크스페이스 이름 수정 API (PATCH /api/workspaces/{workspace_id})
 */
export async function updateWorkspaceApi(
  workspaceId: string,
  name: string
): Promise<UpdateWorkspaceResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      workspace: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name }),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "워크스페이스 수정에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "수정 권한이 없습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        workspace: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      workspace: data.workspace || data,
      message: data.message || "수정 완료",
      error: null,
    };
  } catch (error) {
    console.error("updateWorkspaceApi error:", error);
    return {
      status: "error",
      workspace: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 워크스페이스 삭제 API (DELETE /api/workspaces/{workspace_id})
 */
export async function deleteWorkspaceApi(
  workspaceId: string
): Promise<DeleteWorkspaceResponse> {
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
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}`, {
      method: "DELETE",
    });

    if (response.status === 204) {
      return {
        status: "success",
        message: "삭제 성공",
        error: null,
      };
    }

    const textData = await response.text();
    const data = textData ? JSON.parse(textData) : {};

    if (!response.ok || data.status === "error") {
      let defaultMsg = "워크스페이스 삭제에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "삭제 권한이 없습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
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
    console.error("deleteWorkspaceApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 5. 워크스페이스 멤버 목록 조회 API (GET /api/workspaces/{workspace_id}/members)
 */
export async function getWorkspaceMembersApi(
  workspaceId: string
): Promise<GetWorkspaceMembersResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      members: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/members`,
      {
        method: "GET",
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "멤버 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        members: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      members: data.members || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getWorkspaceMembersApi error:", error);
    return {
      status: "error",
      members: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 6. 워크스페이스 팀원 초대 API (POST /api/workspaces/{workspace_id}/members/invite)
 *
 * owner만 호출 가능. 이미 가입된 사용자면 즉시 추가되고(result: "added"), 미가입
 * 이메일이면 회원가입 링크가 담긴 초대 메일이 발송된다(result: "invited", 7일 유효).
 */
export async function inviteWorkspaceMemberApi(
  workspaceId: string,
  email: string,
  role: "owner" | "member" = "member"
): Promise<InviteWorkspaceMemberResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      result: null,
      member: null,
      email: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/members/invite`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, role }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let errorMsg = data.message || "팀원 초대에 실패했습니다.";

      if (response.status === 409) {
        errorMsg = "이미 워크스페이스에 속한 사용자입니다.";
      } else if (response.status === 401) {
        errorMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        errorMsg = "팀원 초대 권한이 없습니다. (Owner만 가능)";
      } else if (response.status === 404) {
        errorMsg = "존재하지 않는 워크스페이스입니다.";
      } else if (response.status === 422) {
        errorMsg = "이메일 형식을 확인해 주세요.";
      }

      return {
        status: "error",
        result: null,
        member: null,
        email: null,
        message: errorMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    const result: "added" | "invited" = data.status === "invited" ? "invited" : "added";

    return {
      status: "success",
      result,
      member: data.member ?? null,
      email: data.email ?? null,
      message: result === "invited" ? "초대 메일을 발송했습니다." : "팀원이 추가되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("inviteWorkspaceMemberApi error:", error);
    return {
      status: "error",
      result: null,
      member: null,
      email: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 7. 워크스페이스 멤버 역할 변경 API (PATCH /api/workspaces/{workspace_id}/members/{user_id})
 */
export async function updateMemberRoleApi(
  workspaceId: string,
  userId: string,
  role: "owner" | "member"
): Promise<UpdateMemberRoleResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      member: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/members/${userId}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ role }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let errorMsg = data.message || "멤버 역할 변경에 실패했습니다.";

      if (data.error === "last_owner_demotion" || response.status === 400) {
        errorMsg = "마지막 남은 소유자(Owner) 권한은 강등할 수 없습니다.";
      } else if (response.status === 401) {
        errorMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        errorMsg = "멤버 권한 변경 권한이 없습니다. (Owner만 가능)";
      } else if (response.status === 404) {
        errorMsg = "존재하지 않는 워크스페이스이거나 대상 멤버입니다.";
      }

      return {
        status: "error",
        member: null,
        message: errorMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      member: data.member || data,
      message: data.message || "멤버 역할이 변경되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("updateMemberRoleApi error:", error);
    return {
      status: "error",
      member: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 8. 워크스페이스 멤버 제거 API (DELETE /api/workspaces/{workspace_id}/members/{user_id})
 */
export async function deleteWorkspaceMemberApi(
  workspaceId: string,
  userId: string
): Promise<DeleteWorkspaceMemberResponse> {
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
      `${API_BASE_URL}/api/workspaces/${workspaceId}/members/${userId}`,
      {
        method: "DELETE",
      }
    );

    if (response.status === 204) {
      return {
        status: "success",
        message: "멤버가 성공적으로 제거되었습니다.",
        error: null,
      };
    }

    const textData = await response.text();
    const data = textData ? JSON.parse(textData) : {};

    if (!response.ok || data.status === "error") {
      let errorMsg = data.message || "멤버 제거에 실패했습니다.";

      if (data.error === "last_owner_removal" || response.status === 400) {
        errorMsg = "마지막 남은 소유자(Owner)는 제거할 수 없습니다.";
      } else if (response.status === 401) {
        errorMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        errorMsg = "멤버 제거 권한이 없습니다. (Owner만 가능)";
      } else if (response.status === 404) {
        errorMsg = "존재하지 않는 워크스페이스이거나 대상 멤버입니다.";
      }

      return {
        status: "error",
        message: errorMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      message: data.message || "멤버가 성공적으로 제거되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("deleteWorkspaceMemberApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}