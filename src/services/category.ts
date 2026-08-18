import { authFetch } from "./auth";

// --- 타입 정의 ---

export interface Category {
  id: string;
  workspace_id: string;
  name: string;
  is_default: boolean;
  display_order: number;
  created_by?: string;
  created_at?: string;
}

export interface GetCategoryListResponse {
  status: "success" | "error";
  categories: Category[];
  message: string;
  error: string | null;
}

export interface CreateCategoryResponse {
  status: "success" | "error";
  category: Category | null;
  message: string;
  error: string | null;
}

export interface UpdateCategoryResponse {
  status: "success" | "error";
  category: Category | null;
  message: string;
  error: string | null;
}

export interface DeleteCategoryResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// 2026-08-12 기준 백엔드 스펙 확정: GET/POST /workspaces/{id}/categories,
// PATCH/DELETE /categories/{id}. 응답은 status/message로 감싸지 않고
// 카테고리 리소스(또는 {categories: [...]})를 그대로 반환한다.
// ----------------------------------------------------------------------

/**
 * 1. 카테고리 목록 조회 API (GET /api/workspaces/{workspace_id}/categories)
 */
export async function getCategoryListApi(workspaceId: string): Promise<GetCategoryListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      categories: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/categories`,
      {
        method: "GET",
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "카테고리 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        categories: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      categories: data.categories || [],
      message: data.message || "성공",
      error: null,
    };
  } catch (error) {
    console.error("getCategoryListApi error:", error);
    return {
      status: "error",
      categories: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 카테고리 생성 API (POST /api/workspaces/{workspace_id}/categories)
 */
export async function createCategoryApi(
  workspaceId: string,
  name: string
): Promise<CreateCategoryResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      category: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/categories`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "카테고리 생성에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 카테고리를 생성할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      } else if (response.status === 422) {
        defaultMsg = "카테고리 이름은 1~100자로 입력해 주세요.";
      }

      return {
        status: "error",
        category: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      category: data.category || data,
      message: data.message || "카테고리가 생성되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("createCategoryApi error:", error);
    return {
      status: "error",
      category: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 카테고리 이름/순서 수정 API (PATCH /api/categories/{category_id})
 */
export async function updateCategoryApi(
  categoryId: string,
  updates: { name?: string; display_order?: number }
): Promise<UpdateCategoryResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      category: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/categories/${categoryId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(updates),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "카테고리 수정에 실패했습니다.";
      if (response.status === 400) {
        defaultMsg = "수정할 이름 또는 순서를 입력해 주세요.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 수정할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 카테고리입니다.";
      } else if (response.status === 422) {
        defaultMsg = "카테고리 이름은 1~100자로 입력해 주세요.";
      }

      return {
        status: "error",
        category: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      category: data.category || data,
      message: data.message || "수정 완료",
      error: null,
    };
  } catch (error) {
    console.error("updateCategoryApi error:", error);
    return {
      status: "error",
      category: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 카테고리 삭제 API (DELETE /api/categories/{category_id})
 * 기본 카테고리(is_default=true)는 삭제할 수 없다 — 백엔드에서 400으로 응답.
 */
export async function deleteCategoryApi(categoryId: string): Promise<DeleteCategoryResponse> {
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
    const response = await authFetch(`${API_BASE_URL}/api/categories/${categoryId}`, {
      method: "DELETE",
    });

    if (response.status === 204) {
      return {
        status: "success",
        message: "카테고리가 삭제되었습니다.",
        error: null,
      };
    }

    const textData = await response.text();
    const data = textData ? JSON.parse(textData) : {};

    if (!response.ok || data.status === "error") {
      let defaultMsg = "카테고리 삭제에 실패했습니다.";
      if (response.status === 400) {
        defaultMsg = "기본 카테고리는 삭제할 수 없습니다.";
      } else if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 삭제할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 카테고리입니다.";
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
    console.error("deleteCategoryApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}
