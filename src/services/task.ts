// src/services/task.ts
import { authFetch } from "./auth";

// --- 타입 정의 ---

export type BackendTaskStatus = "open" | "in_progress" | "done" | "cancelled" | "suggested";
export type TaskPriority = "low" | "medium" | "high";

export interface BackendTask {
  id: string;
  workspace_id: string;
  meeting_id?: string | null;
  title: string;
  description?: string | null;
  assignee_id?: string | null;
  assignee_label?: string | null;
  priority?: TaskPriority | null;
  status: BackendTaskStatus;
  due_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface GetTaskListResponse {
  status: "success" | "error";
  tasks: BackendTask[];
  message: string;
  error: string | null;
}

export interface TaskResponse {
  status: "success" | "error";
  task: BackendTask | null;
  message: string;
  error: string | null;
}

export interface DeleteTaskResponse {
  status: "success" | "error";
  message: string;
  error: string | null;
}

export interface CreateTaskParams {
  title: string;
  description?: string;
  assignee_id?: string;
  assignee_label?: string;
  priority?: TaskPriority;
  due_at?: string;
}

export interface UpdateTaskParams {
  title?: string;
  description?: string | null;
  assignee_id?: string | null;
  assignee_label?: string | null;
  priority?: TaskPriority;
  status?: BackendTaskStatus;
  due_at?: string | null;
}

// ----------------------------------------------------------------------
// API 함수 목록
// ----------------------------------------------------------------------

/**
 * 1. 할 일 목록 조회 API (GET /api/workspaces/{workspace_id}/tasks)
 */
export async function getTaskListApi(workspaceId: string): Promise<GetTaskListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      tasks: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/tasks`, {
      method: "GET",
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "할 일 목록을 불러오지 못했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 조회할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      }

      return {
        status: "error",
        tasks: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      tasks: data.tasks || [],
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getTaskListApi error:", error);
    return {
      status: "error",
      tasks: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 2. 할 일 생성 API (POST /api/workspaces/{workspace_id}/tasks)
 */
export async function createTaskApi(
  workspaceId: string,
  params: CreateTaskParams
): Promise<TaskResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      task: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    });

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "할 일 생성에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 생성할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스입니다.";
      } else if (response.status === 422) {
        defaultMsg = "할 일 제목을 200자 이내로 입력해 주세요.";
      } else if (response.status === 500) {
        defaultMsg = "워크스페이스의 기본 카테고리를 찾을 수 없습니다.";
      }

      return {
        status: "error",
        task: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      task: data.task || data,
      message: "할 일이 생성되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("createTaskApi error:", error);
    return {
      status: "error",
      task: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 3. 할 일 전체 정보 수정 API (PATCH /api/workspaces/{workspace_id}/tasks/{task_id})
 */
export async function updateTaskApi(
  workspaceId: string,
  taskId: string,
  params: UpdateTaskParams
): Promise<TaskResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      task: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/tasks/${taskId}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "업무 수정에 실패했습니다.";
      if (response.status === 400) {
        defaultMsg = "수정할 값이 전달되지 않았습니다.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 수정할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 업무입니다.";
      }

      return {
        status: "error",
        task: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      task: data.task || data,
      message: "업무가 수정되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("updateTaskApi error:", error);
    return {
      status: "error",
      task: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 4. 할 일 상태 변경 API (PATCH /api/workspaces/{workspace_id}/tasks/{task_id}/status)
 */
export async function updateTaskStatusApi(
  workspaceId: string,
  taskId: string,
  status: BackendTaskStatus
): Promise<TaskResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      task: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/tasks/${taskId}/status`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "할 일 상태 변경에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 변경할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 할 일입니다.";
      } else if (response.status === 422) {
        defaultMsg = "잘못된 상태 값입니다.";
      }

      return {
        status: "error",
        task: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      task: data.task || data,
      message: "상태가 변경되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("updateTaskStatusApi error:", error);
    return {
      status: "error",
      task: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 5. 할 일 우선순위 변경 API (PATCH /api/workspaces/{workspace_id}/tasks/{task_id}/priority)
 */
export async function updateTaskPriorityApi(
  workspaceId: string,
  taskId: string,
  priority: TaskPriority
): Promise<TaskResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      task: null,
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/tasks/${taskId}/priority`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ priority }),
      }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "우선순위 변경에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 변경할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 할 일입니다.";
      } else if (response.status === 422) {
        defaultMsg = "잘못된 우선순위 값입니다.";
      }

      return {
        status: "error",
        task: null,
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      task: data.task || data,
      message: "우선순위가 변경되었습니다.",
      error: null,
    };
  } catch (error) {
    console.error("updateTaskPriorityApi error:", error);
    return {
      status: "error",
      task: null,
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 6-1. 회의에서 추출된 제안된 할 일 목록 조회 API
 * (GET /api/workspaces/{workspace_id}/meetings/{meeting_id}/suggested-tasks)
 * status가 "suggested"인 할 일은 일반 할 일 목록 조회에선 제외되므로 이 API로 따로 조회한다.
 * 승인은 기존 상태 변경 API(updateTaskStatusApi)로 "open"으로 바꾸면 되고, 거절은 삭제하면 된다.
 */
export async function getSuggestedTasksApi(
  workspaceId: string,
  meetingId: string
): Promise<GetTaskListResponse> {
  const API_BASE_URL = import.meta.env.VITE_API_URL || "";
  const token = localStorage.getItem("access_token");

  if (!token) {
    return {
      status: "error",
      tasks: [],
      message: "인증 토큰이 없습니다. 다시 로그인해 주세요.",
      error: "UNAUTHORIZED",
    };
  }

  try {
    const response = await authFetch(
      `${API_BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/suggested-tasks`,
      { method: "GET" }
    );

    const data = await response.json();

    if (!response.ok || data.status === "error") {
      let defaultMsg = "제안된 할 일을 불러오지 못했습니다.";
      if (response.status === 401) defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      else if (response.status === 404) defaultMsg = "존재하지 않는 회의입니다.";

      return {
        status: "error",
        tasks: [],
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      tasks: data.tasks || [],
      message: "성공",
      error: null,
    };
  } catch (error) {
    console.error("getSuggestedTasksApi error:", error);
    return {
      status: "error",
      tasks: [],
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}

/**
 * 6. 할 일 삭제 API (DELETE /api/workspaces/{workspace_id}/tasks/{task_id})
 */
export async function deleteTaskApi(workspaceId: string, taskId: string): Promise<DeleteTaskResponse> {
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
    const response = await authFetch(`${API_BASE_URL}/api/workspaces/${workspaceId}/tasks/${taskId}`, {
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
      let defaultMsg = "할 일 삭제에 실패했습니다.";
      if (response.status === 401) {
        defaultMsg = "인증이 만료되었습니다. 다시 로그인해 주세요.";
      } else if (response.status === 403) {
        defaultMsg = "워크스페이스 멤버만 삭제할 수 있습니다.";
      } else if (response.status === 404) {
        defaultMsg = "존재하지 않는 워크스페이스이거나 할 일입니다.";
      }

      return {
        status: "error",
        message: data.message || defaultMsg,
        error: data.error || `HTTP_${response.status}`,
      };
    }

    return {
      status: "success",
      message: "삭제 성공",
      error: null,
    };
  } catch (error) {
    console.error("deleteTaskApi error:", error);
    return {
      status: "error",
      message: "서버와 통신할 수 없습니다.",
      error: "NETWORK_ERROR",
    };
  }
}