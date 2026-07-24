// src/components/CreateTaskModal.tsx
import { useEffect, useRef, useState } from "react";
import { Task, TaskPriority, TaskStatus } from "../types";
import { CloseIcon } from "./icons";
import { getWorkspaceMembersApi } from "../services/workspace";

interface Props {
  workspaceId?: string;
  initialStatus?: TaskStatus; // 👈 클릭한 컬럼의 초기 상태값
  onClose: () => void;
  onCreate: (task: Omit<Task, "id">) => void;
  t: any;
}

interface FormState {
  task: string;
  description: string;
  assignee: string;
  deadline: string;
  priority: TaskPriority;
  status: TaskStatus;
}

function formatDisplayDate(dateStr: string, isKo: boolean): string {
  if (!dateStr) return "";
  const parts = dateStr.split("-");
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

export default function CreateTaskModal({ workspaceId, initialStatus = "todo", onClose, onCreate, t }: Props) {
  const isKo = t.settings_lang === "언어";

  const INITIAL_FORM: FormState = {
    task: "",
    description: "",
    assignee: "",
    deadline: "",
    priority: "medium",
    status: initialStatus, // 👈 전달된 컬럼 상태로 설정
  };

  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [error, setError] = useState<string | null>(null);

  const [memberList, setMemberList] = useState<string[]>([]);
  const [isAssigneeOpen, setIsAssigneeOpen] = useState(false);
  const assigneeRef = useRef<HTMLDivElement>(null);
  const dateInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    async function fetchMembers() {
      if (!workspaceId) return;
      const res = await getWorkspaceMembersApi(workspaceId);
      if (res.status === "success" && res.members) {
        const names = res.members
          .map((m) => m.display_name || m.username)
          .filter(Boolean);
        setMemberList(names);
      }
    }
    fetchMembers();
  }, [workspaceId]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (assigneeRef.current && !assigneeRef.current.contains(e.target as Node)) {
        setIsAssigneeOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleChange<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  const filteredMembers = memberList.filter((name) =>
    name.toLowerCase().includes(form.assignee.trim().toLowerCase())
  );

  function handleSubmit() {
    if (!form.task.trim()) {
      setError(t.modal_error_empty);
      return;
    }

    onCreate({
      task: form.task.trim(),
      description: form.description.trim() || null,
      assignee: form.assignee.trim() || null,
      deadline: form.deadline.trim() || null,
      status: form.status,
      priority: form.priority,
    });
    onClose();
  }

  function handleOpenDatePicker() {
    const el = dateInputRef.current;
    if (!el) return;

    const input = el as HTMLInputElement & { showPicker?: () => void };
    if (typeof input.showPicker === "function") {
      input.showPicker();
    } else {
      input.focus();
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl border border-recall-border bg-recall-bg p-5 shadow-xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <p className="text-base font-semibold text-recall-text">{t.modal_add_task_title}</p>
          <button onClick={onClose} className="flex h-6 w-6 items-center justify-center rounded hover:bg-white/5">
            <CloseIcon size={14} className="text-recall-textMuted" />
          </button>
        </div>

        <div className="flex flex-col gap-3">
          {/* 업무 제목 */}
          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">
              {t.modal_task_content} <span className="text-recall-danger">*</span>
            </label>
            <input
              value={form.task}
              onChange={(e) => handleChange("task", e.target.value)}
              placeholder={t.modal_task_content_placeholder}
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
          </div>

          {/* 부가 설명 (상세 내용) */}
          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">상세 설명</label>
            <textarea
              rows={3}
              value={form.description}
              onChange={(e) => handleChange("description", e.target.value)}
              placeholder="업무에 필요한 추가 내용이나 설명글을 적어주세요."
              className="w-full resize-none rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />
          </div>

          {/* 담당자 */}
          <div className="relative" ref={assigneeRef}>
            <label className="mb-1 block text-sm text-recall-textMuted">{t.modal_assignee}</label>
            <input
              value={form.assignee}
              onFocus={() => setIsAssigneeOpen(true)}
              onChange={(e) => {
                handleChange("assignee", e.target.value);
                setIsAssigneeOpen(true);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  setIsAssigneeOpen(false);
                }
              }}
              placeholder={t.modal_assignee_placeholder}
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
            />

            {isAssigneeOpen && filteredMembers.length > 0 && (
              <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-40 overflow-y-auto rounded-xl border border-recall-border bg-recall-bgSoft py-1 shadow-xl">
                {filteredMembers.map((memberName) => (
                  <button
                    key={memberName}
                    type="button"
                    onClick={() => {
                      handleChange("assignee", memberName);
                      setIsAssigneeOpen(false);
                    }}
                    className="flex w-full items-center px-3 py-2 text-left text-sm hover:bg-white/5 transition"
                  >
                    <span>{memberName}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 마감일 */}
          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">{t.modal_deadline}</label>
            <div
              onClick={handleOpenDatePicker}
              className="relative w-full cursor-pointer rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-sm min-h-[34px] flex items-center justify-between hover:border-recall-accent transition"
            >
              <span className={form.deadline ? "text-recall-text" : "text-recall-textMuted"}>
                {form.deadline
                  ? formatDisplayDate(form.deadline, isKo)
                  : isKo
                  ? "월-일 선택"
                  : "Select YYYY-MM-DD"}
              </span>

              <CalendarIcon className="text-recall-textMuted flex-shrink-0" size={14} />

              <input
                ref={dateInputRef}
                type="date"
                value={form.deadline}
                onChange={(e) => handleChange("deadline", e.target.value)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer pointer-events-auto"
              />
            </div>
          </div>

          {/* 우선순위 */}
          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">{t.modal_priority}</label>
            <select
              value={form.priority}
              onChange={(e) => handleChange("priority", e.target.value as TaskPriority)}
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-sm text-recall-text focus:outline-none focus:border-recall-accent"
            >
              <option value="high">{t.priority_high}</option>
              <option value="medium">{t.priority_medium}</option>
              <option value="low">{t.priority_low}</option>
            </select>
          </div>
        </div>

        {error && <p className="mt-3 text-sm text-recall-danger">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-recall-border px-4 py-2 text-sm text-recall-textMuted hover:bg-white/5"
          >
            {t.task_cancel}
          </button>
          <button
            onClick={handleSubmit}
            className="rounded-lg bg-recall-accent px-4 py-2 text-sm text-white hover:opacity-90 font-medium"
          >
            {t.modal_btn_add}
          </button>
        </div>
      </div>
    </div>
  );
}