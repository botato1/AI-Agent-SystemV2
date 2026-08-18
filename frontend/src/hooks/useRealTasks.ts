// src/hooks/useRealTasks.ts
import { useEffect, useRef, useState } from "react";
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

const POLL_INTERVAL_MS = 15000;

function toBackendStatus(status: TaskStatus): BackendTaskStatus {
  return status === "todo" ? "open" : status;
}

function toLocalStatus(status: BackendTaskStatus): TaskStatus {
  // "suggested"는 loadTasks에서 미리 걸러내므로 여기 들어올 일이 없다 - 타입만 맞춰주는 방어 코드
  if (status === "open" || status === "suggested") return "todo";
  return status;
}

// 서버가 주는 due_at(UTC ISO)을 로컬 시간 기준 "YYYY-MM-DDTHH:mm" 문자열로 바꾼다.
// <input type="date">/<input type="time"> 값이랑 그대로 맞물리게 하기 위함 - 여기서
// 잘라서 날짜만 남기면 시간 정보가 없어지므로, 항상 날짜+시간을 함께 보존한다.
function toLocalDateTimeInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// 시간을 안 정한 마감일(날짜만, "T" 없음)은 자정(로컬 기준)으로 저장한다 - 그냥 new Date("2026-08-12")로
// 넘기면 UTC 자정으로 해석돼서, 한국 시간대에서 되돌아올 때 09:00으로 둔갑해버린다(9시가 도로
// 나타나는 원인). "T00:00"을 붙여 로컬 자정으로 명시하면 왕복해도 그대로 자정으로 남는다.
function toIsoDeadline(deadline: string): string {
  const withTime = deadline.includes("T") ? deadline : `${deadline}T00:00`;
  return new Date(withTime).toISOString();
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
    category_id: bt.category_id ?? null,
  };
}

export function useRealTasks(
  workspaceId: string,
  memberNameById: Record<string, string>,
  selectedCategoryId?: string | null
) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  // 방금 내가 직접 바꾼(생성/수정/상태변경/삭제) 시각 - 백그라운드 폴링 요청이 그 이후에도
  // 계속 날아가고 있다가, 변경이 반영되기 "전" 스냅샷을 늦게 받아서 방금 한 변경을 조용히
  // 되돌려버리는 경우가 있었다("완료로 옮겼는데 사라진다"는 게 이 레이스 컨디션이었음).
  // 요청을 시작한 시점이 마지막 로컬 변경보다 이르면 그 응답은 낡은 것이니 무시한다.
  const lastMutationAtRef = useRef(0);

  async function loadTasks() {
    if (!workspaceId) return;
    const requestStartedAt = Date.now();
    // status=all로 done/cancelled/suggested까지 다 받아온다 (칸반보드 "완료" 칸에 필요)
    const res = await getTaskListApi(workspaceId, true, selectedCategoryId ?? undefined);
    if (requestStartedAt < lastMutationAtRef.current) return;
    if (res.status === "success") {
      // "suggested"(회의에서 제안됐지만 아직 승인 안 된 항목)는 회의 화면의 별도 승인
      // 플로우에서 다루는 것이라, 칸반보드에 미리 보이면 승인 전인데 할 일처럼 보여 혼동을
      // 준다 - 여기선 제외한다.
      const boardTasks = res.tasks.filter((t) => t.status !== "suggested");
      setTasks(boardTasks.map((t) => toLocalTask(t, memberNameById)));
    }
  }

  useEffect(() => {
    setIsLoading(true);
    loadTasks().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, selectedCategoryId]);

  // 다른 팀원이 추가/수정/삭제한 할 일은 내 화면엔 신호가 안 오므로(전용 웹소켓 없음),
  // 알림벨과 같은 방식으로 백그라운드에서 조용히 주기적 재조회해서 새로고침 없이 반영한다
  useEffect(() => {
    if (!workspaceId) return;
    const timer = setInterval(loadTasks, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, selectedCategoryId]);

  // 1. 생성
  async function createTask(input: Omit<Task, "id">) {
    const res = await createTaskApi(workspaceId, {
      title: input.task,
      description: input.description || undefined,
      assignee_label: input.assignee || undefined,
      priority: input.priority,
      status: toBackendStatus(input.status),
      due_at: input.deadline ? toIsoDeadline(input.deadline) : undefined,
    });

    if (res.status === "success" && res.task) {
      let created = res.task as BackendTask;
      const wantedStatus = toBackendStatus(input.status);
      // 일부 생성 API는 status 필드를 받아도 무시하고 항상 기본 상태로 만드는 경우가 있다 -
      // "완료"를 선택해 만들었는데 "해야 할 일"에 생기는 문제가 여기서 나므로, 생성 직후
      // 상태가 원하는 값과 다르면 상태 변경 API로 한 번 더 강제로 맞춰준다.
      if (created.status !== wantedStatus) {
        const statusRes = await updateTaskStatusApi(workspaceId, created.id, wantedStatus);
        if (statusRes.status === "success" && statusRes.task) {
          created = statusRes.task as BackendTask;
        }
      }
      lastMutationAtRef.current = Date.now();
      setTasks((prev) => [toLocalTask(created, memberNameById), ...prev]);
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
      due_at: updatedTask.deadline ? toIsoDeadline(updatedTask.deadline) : null,
    };

    const res = await updateTaskApi(workspaceId, updatedTask.id, payload);

    if (res.status === "success") {
      const rawTask = res.task || (res as unknown as BackendTask);
      const updatedLocalTask = rawTask && rawTask.id ? toLocalTask(rawTask, memberNameById) : updatedTask;

      lastMutationAtRef.current = Date.now();
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
      lastMutationAtRef.current = Date.now();
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
      lastMutationAtRef.current = Date.now();
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
      lastMutationAtRef.current = Date.now();
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
    refetchTasks: loadTasks,
  };
}