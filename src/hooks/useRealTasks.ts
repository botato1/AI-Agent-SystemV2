// src/hooks/useRealTasks.ts
import { useEffect, useState } from "react";
import { Task, TaskStatus, TaskPriority } from "../types";
import {
  BackendTask,
  BackendTaskStatus,
  UpdateTaskParams,
  getTaskListApi,
  createTaskApi,
  updateTaskApi,
  updateTaskStatusApi,
  updateTaskPriorityApi,
  deleteTaskApi,
} from "../services/task";

function toBackendStatus(status: TaskStatus): BackendTaskStatus {
  return status === "todo" ? "open" : status;
}

function toLocalStatus(status: BackendTaskStatus): TaskStatus {
  return status === "open" ? "todo" : status;
}

// 서버가 주는 due_at(UTC ISO)을 로컬 시간 기준 "YYYY-MM-DDTHH:mm" 문자열로 바꾼다.
// <input type="date">/<input type="time"> 값이랑 그대로 맞물리게 하기 위함 - 여기서
// 잘라서 날짜만 남기면 시간 정보가 없어지므로, 항상 날짜+시간을 함께 보존한다.
function toLocalDateTimeInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function toLocalTask(bt: BackendTask, memberNameById: Record<string, string>): Task {
  return {
    id: bt.id,
    task: bt.title,
    description: bt.description || null,
    assignee: bt.assignee_label || (bt.assignee_id ? memberNameById[bt.assignee_id] : null) || null,
    deadline: bt.due_at ? toLocalDateTimeInput(bt.due_at) : null,
    status: toLocalStatus(bt.status),
    priority: bt.priority ?? "medium",
  };
}

export function useRealTasks(workspaceId: string, memberNameById: Record<string, string>) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  async function loadTasks() {
    if (!workspaceId) return;
    const res = await getTaskListApi(workspaceId);
    if (res.status === "success") {
      setTasks(res.tasks.map((t) => toLocalTask(t, memberNameById)));
    }
  }

  useEffect(() => {
    setIsLoading(true);
    loadTasks().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  // 1. 생성
  async function createTask(input: Omit<Task, "id">) {
    const res = await createTaskApi(workspaceId, {
      title: input.task,
      description: input.description || undefined,
      assignee_label: input.assignee || undefined,
      priority: input.priority,
      due_at: input.deadline ? new Date(input.deadline).toISOString() : undefined,
    });

    if (res.status === "success" && res.task) {
      setTasks((prev) => [toLocalTask(res.task as BackendTask, memberNameById), ...prev]);
    } else {
      alert(`할 일 생성 실패: ${res.message}`);
    }
  }

  // 2. 전체 수정
  async function updateTask(updatedTask: Task) {
    const payload: UpdateTaskParams = {
      title: updatedTask.task,
      description: updatedTask.description ? updatedTask.description : null,
      assignee_label: updatedTask.assignee ? updatedTask.assignee : null,
      priority: updatedTask.priority,
      status: toBackendStatus(updatedTask.status),
      due_at: updatedTask.deadline ? new Date(updatedTask.deadline).toISOString() : null,
    };

    const res = await updateTaskApi(workspaceId, updatedTask.id, payload);

    if (res.status === "success") {
      const rawTask = res.task || (res as unknown as BackendTask);
      const updatedLocalTask = rawTask && rawTask.id ? toLocalTask(rawTask, memberNameById) : updatedTask;

      setTasks((prev) =>
        prev.map((t) => (t.id === updatedTask.id ? updatedLocalTask : t))
      );
    } else {
      alert(`업무 수정 실패: ${res.message}`);
    }
  }

  // 3. 상태 변경
  async function changeStatus(taskId: string, newStatus: TaskStatus) {
    const res = await updateTaskStatusApi(workspaceId, taskId, toBackendStatus(newStatus));
    if (res.status === "success" && res.task) {
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? toLocalTask(res.task as BackendTask, memberNameById) : t))
      );
    } else {
      alert(`상태 변경 실패: ${res.message}`);
    }
  }

  // 4. 우선순위 변경
  async function changePriority(taskId: string, newPriority: TaskPriority) {
    const res = await updateTaskPriorityApi(workspaceId, taskId, newPriority);
    if (res.status === "success" && res.task) {
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? toLocalTask(res.task as BackendTask, memberNameById) : t))
      );
    } else {
      alert(`우선순위 변경 실패: ${res.message}`);
    }
  }

  // 5. 삭제
  async function removeTask(taskId: string) {
    const res = await deleteTaskApi(workspaceId, taskId);
    if (res.status === "success") {
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
    } else {
      alert(`삭제 실패: ${res.message}`);
    }
  }

  // 💡 반환 객체에 명확히 매핑
  return {
    tasks,
    isLoading,
    createTask,
    updateTask,
    changeStatus,
    changePriority,
    removeTask,
  };
}