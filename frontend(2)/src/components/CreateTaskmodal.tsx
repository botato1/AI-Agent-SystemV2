// src/components/CreateTaskModal.tsx
import { useState } from "react";
import { Task, TaskPriority, TaskStatus } from "../types";
import { CloseIcon } from "./icons";

interface Props {
  onClose: () => void;
  onCreate: (task: Omit<Task, "id">) => void;
  t: any;
}

interface FormState {
  task: string;
  assignee: string;
  deadline: string;
  status: TaskStatus;
  priority: TaskPriority;
}

// 화면에 연도 없이 날짜를 다국어로 예쁘게 출력해주는 헬퍼 함수
function formatDisplayDate(dateStr: string, isKo: boolean): string {
  if (!dateStr) return "";
  const parts = dateStr.split("-"); // yyyy-mm-dd 구조 파싱
  if (parts.length === 3) {
    const month = parseInt(parts[1], 10);
    const day = parseInt(parts[2], 10);
    if (!isNaN(month) && !isNaN(day)) {
      return isKo 
        ? `${month}월 ${day}일` 
        : `${String(month).padStart(2, "0")}/${String(day).padStart(2, "0")}`;
    }
  }
  return dateStr;
}

// 달력 미니 아이콘 컴포넌트 내장 정의
function CalendarIcon({ size = 14, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
      <line x1="16" y1="2" x2="16" y2="6"></line>
      <line x1="8" y1="2" x2="8" y2="6"></line>
      <line x1="3" y1="10" x2="21" y2="10"></line>
    </svg>
  );
}

export default function CreateTaskModal({ onClose, onCreate, t }: Props) {
  const isKo = t.settings_lang === "언어";

  const INITIAL_FORM: FormState = {
    task: "",
    assignee: "",
    deadline: "",
    status: "todo",
    priority: "medium",
  };

  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [error, setError] = useState<string | null>(null);

  function handleChange<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit() {
    if (!form.task.trim()) {
      setError(t.modal_error_empty);
      return;
    }

    onCreate({
      task: form.task.trim(),
      assignee: form.assignee.trim() || null,
      deadline: form.deadline.trim() || null,
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
          <p className="text-sm font-semibold text-recall-text">{t.modal_add_task_title}</p>
          <button onClick={onClose} className="flex h-6 w-6 items-center justify-center rounded hover:bg-white/5">
            <CloseIcon size={14} className="text-recall-textMuted" />
          </button>
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">
              {t.modal_task_content} <span className="text-recall-danger">*</span>
            </label>
            <input
              value={form.task}
              onChange={(e) => handleChange("task", e.target.value)}
              placeholder={t.modal_task_content_placeholder}
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">{t.modal_assignee}</label>
            <input
              value={form.assignee}
              onChange={(e) => handleChange("assignee", e.target.value)}
              placeholder={t.modal_assignee_placeholder}
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
          </div>

          {/* 마감일 입력 영역 - 아이콘 레이아웃 탑재 */}
          <div>
            <label className="mb-1 block text-xs text-recall-textMuted">{t.modal_deadline}</label>
            
            <div className="relative w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text min-h-[34px] flex items-center justify-between hover:border-recall-accent transition">
              {/* 1. 사용자의 눈에 보이는 가짜 날짜 텍스트 영역 */}
              <span className={form.deadline ? "text-recall-text" : "text-recall-textMuted"}>
                {form.deadline 
                  ? formatDisplayDate(form.deadline, isKo) 
                  : (isKo ? "월-일 선택" : "Select YYYY-MM-DD")
                }
              </span>
              
              {/* 2. 눈에 띄게 배치한 예쁜 달력 아이콘 */}
              <CalendarIcon className="text-recall-textMuted flex-shrink-0" size={14} />
              
              {/* 3. 실제 마우스 클릭 전체 영역을 책임지는 투명 인풋 */}
              <input
                type="date"
                value={form.deadline}
                onChange={(e) => handleChange("deadline", e.target.value)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-recall-textMuted">{t.modal_priority}</label>
              <select
                value={form.priority}
                onChange={(e) => handleChange("priority", e.target.value as TaskPriority)}
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text focus:outline-none focus:border-recall-accent"
              >
                <option value="high">{t.priority_high}</option>
                <option value="medium">{t.priority_medium}</option>
                <option value="low">{t.priority_low}</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-recall-textMuted">{t.modal_status}</label>
              <select
                value={form.status}
                onChange={(e) => handleChange("status", e.target.value as TaskStatus)}
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text focus:outline-none focus:border-recall-accent"
              >
                <option value="todo">{t.status_todo}</option>
                <option value="in_progress">{t.status_in_progress}</option>
                <option value="done">{t.status_done}</option>
                <option value="delayed">{t.status_delayed}</option>
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
            {t.task_cancel}
          </button>
          <button
            onClick={handleSubmit}
            className="rounded-lg bg-recall-accent px-4 py-2 text-xs text-white hover:opacity-90"
          >
            {t.modal_btn_add}
          </button>
        </div>
      </div>
    </div>
  );
}