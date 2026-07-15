import { useState } from "react";
import { Task, TaskPriority, TaskStatus } from "../types";
import { CloseIcon } from "./icons";

interface Props {
  onClose: () => void;
  onCreate: (task: Omit<Task, "id">) => void;
}

interface FormState {
  task: string;
  assignee: string;
  deadline: string;
  status: TaskStatus;
  priority: TaskPriority;
}

const INITIAL_FORM: FormState = {
  task: "",
  assignee: "",
  deadline: "",
  status: "todo",
  priority: "medium",
};

export default function CreateTaskModal({ onClose, onCreate }: Props) {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [error, setError] = useState<string | null>(null);

  function handleChange<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit() {
    if (!form.task.trim()) {
      setError("업무 내용을 입력해주세요.");
      return;
    }
    onCreate({
      task: form.task.trim(),
      assignee: form.assignee.trim() || null,
      deadline: form.deadline || null,
      status: form.status,
      priority: form.priority,
    });
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="mx-4 w-full max-w-md rounded-2xl border border-recall-border bg-recall-bg p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <p className="text-sm font-semibold text-recall-text">새 업무 추가</p>
          <button onClick={onClose} className="flex h-6 w-6 items-center justify-center rounded hover:bg-white/5">
            <CloseIcon size={14} className="text-recall-textMuted" />
          </button>
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">
              업무 내용 <span className="text-recall-danger">*</span>
            </label>
            <input
              value={form.task}
              onChange={(e) => handleChange("task", e.target.value)}
              placeholder="업무 내용을 입력하세요"
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">담당자</label>
            <input
              value={form.assignee}
              onChange={(e) => handleChange("assignee", e.target.value)}
              placeholder="담당자 이름"
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">마감일</label>
            <input
              type="date"
              value={form.deadline}
              onChange={(e) => handleChange("deadline", e.target.value)}
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text focus:outline-none focus:border-recall-accent"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-recall-textMuted">우선순위</label>
              <select
                value={form.priority}
                onChange={(e) => handleChange("priority", e.target.value as TaskPriority)}
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text focus:outline-none focus:border-recall-accent"
              >
                <option value="high">높음</option>
                <option value="medium">중간</option>
                <option value="low">낮음</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-recall-textMuted">상태</label>
              <select
                value={form.status}
                onChange={(e) => handleChange("status", e.target.value as TaskStatus)}
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text focus:outline-none focus:border-recall-accent"
              >
                <option value="todo">해야 할 일</option>
                <option value="in_progress">진행 중</option>
                <option value="done">완료</option>
                <option value="delayed">지연</option>
              </select>
            </div>
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-recall-danger">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-recall-border px-4 py-2 text-xs text-recall-textMuted hover:bg-white/5"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            className="rounded-lg bg-recall-accent px-4 py-2 text-xs text-white hover:opacity-90"
          >
            업무 추가
          </button>
        </div>
      </div>
    </div>
  );
}