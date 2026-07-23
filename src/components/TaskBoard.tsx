// src/components/TaskBoard.tsx
import { useEffect, useRef, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  useDroppable,
  useDraggable,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import { Task, TaskPriority, TaskStatus } from "../types";
import {
  PlusIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  TrashIcon,
  CloseIcon,
  WarningIcon,
} from "./icons";
import { getWorkspaceMembersApi } from "../services/workspace";

interface Props {
  taskList: Task[];
  workspaceId?: string;
  onOpenModal: (status?: TaskStatus) => void;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onPriorityChange: (taskId: string, newPriority: TaskPriority) => void;
  onUpdateTask?: (updatedTask: Task) => void;
  onDelete: (taskId: string) => void;
  t: any;
}

const priorityDotClass: Record<TaskPriority, string> = {
  high: "bg-rose-400",
  medium: "bg-amber-400",
  low: "bg-emerald-400",
};

const priorityWeight: Record<TaskPriority, number> = { high: 0, medium: 1, low: 2 };

type SortMode = "deadline" | "priority" | "custom";

const CUSTOM_ORDER_KEY = "recall-task-custom-order";

function saveCustomOrder(columnId: string, taskIds: string[]) {
  try {
    const all = JSON.parse(localStorage.getItem(CUSTOM_ORDER_KEY) ?? "{}");
    all[columnId] = taskIds;
    localStorage.setItem(CUSTOM_ORDER_KEY, JSON.stringify(all));
  } catch {
    /* 무시 */
  }
}

function loadCustomOrder(columnId: string): string[] {
  try {
    const all = JSON.parse(localStorage.getItem(CUSTOM_ORDER_KEY) ?? "{}");
    return all[columnId] ?? [];
  } catch {
    return [];
  }
}

function formatDeadline(deadline: string | null): string {
  if (!deadline) return "-";
  const parts = deadline.split("-");
  if (parts.length === 3) {
    const month = parseInt(parts[1], 10);
    const day = parseInt(parts[2], 10);
    if (!isNaN(month) && !isNaN(day)) return `${month}월 ${day}일`;
  }
  return "-";
}

function parseDeadline(deadline: string | null): number | null {
  if (!deadline) return null;
  const parsed = new Date(deadline).getTime();
  return isNaN(parsed) ? null : parsed;
}

function isOverdue(deadline: string | null): boolean {
  if (!deadline) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const due = new Date(deadline);
  due.setHours(0, 0, 0, 0);

  return due < today;
}

function sortByDeadline(tasks: Task[]): Task[] {
  return [...tasks].sort((a, b) => {
    const aOverdue = isOverdue(a.deadline) && a.status !== "done";
    const bOverdue = isOverdue(b.deadline) && b.status !== "done";

    if (aOverdue && !bOverdue) return -1;
    if (!aOverdue && bOverdue) return 1;

    const aTime = parseDeadline(a.deadline);
    const bTime = parseDeadline(b.deadline);
    if (aTime !== null && bTime === null) return -1;
    if (aTime === null && bTime !== null) return 1;
    if (aTime !== null && bTime !== null && aTime !== bTime) return aTime - bTime;
    return priorityWeight[a.priority] - priorityWeight[b.priority];
  });
}

function sortByPriority(tasks: Task[]): Task[] {
  return [...tasks].sort((a, b) => {
    const aOverdue = isOverdue(a.deadline) && a.status !== "done";
    const bOverdue = isOverdue(b.deadline) && b.status !== "done";

    if (aOverdue && !bOverdue) return -1;
    if (!aOverdue && bOverdue) return 1;

    if (priorityWeight[a.priority] !== priorityWeight[b.priority]) {
      return priorityWeight[a.priority] - priorityWeight[b.priority];
    }
    const aTime = parseDeadline(a.deadline);
    const bTime = parseDeadline(b.deadline);
    if (aTime !== null && bTime === null) return -1;
    if (aTime === null && bTime !== null) return 1;
    if (aTime !== null && bTime !== null) return aTime - bTime;
    return 0;
  });
}

function sortByCustomOrder(tasks: Task[], order: string[]): Task[] {
  const indexMap = new Map(order.map((id, i) => [id, i]));
  return [...tasks].sort((a, b) => {
    const aIdx = indexMap.has(a.id) ? indexMap.get(a.id)! : Infinity;
    const bIdx = indexMap.has(b.id) ? indexMap.get(b.id)! : Infinity;
    return aIdx - bIdx;
  });
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

function TaskDetailModal({
  task,
  workspaceId,
  onClose,
  onSave,
  onDelete,
  t,
}: {
  task: Task;
  workspaceId?: string;
  onClose: () => void;
  onSave: (updatedTask: Task) => void;
  onDelete: (id: string) => void;
  t: any;
}) {
  const [form, setForm] = useState<Task>({ ...task });
  const [memberList, setMemberList] = useState<string[]>([]);
  const [isAssigneeOpen, setIsAssigneeOpen] = useState(false);

  const assigneeRef = useRef<HTMLDivElement>(null);
  const dateInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setForm({ ...task });
  }, [task]);

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

  const filteredMembers = memberList.filter((name) =>
    name.toLowerCase().includes((form.assignee || "").trim().toLowerCase())
  );

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

  function handleSave() {
    if (!form.task.trim()) return;
    onSave(form);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-2xl border border-recall-border bg-recall-bg p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between border-b border-recall-border pb-3">
          <p className="text-sm font-semibold text-recall-text">업무 상세 및 수정</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        <div className="flex flex-col gap-4 max-h-[75vh] overflow-y-auto pr-1">
          <div>
            <label className="mb-1 block text-xs font-semibold text-recall-textMuted">업무 제목</label>
            <input
              value={form.task}
              onChange={(e) => setForm({ ...form, task: e.target.value })}
              className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-sm text-recall-text font-medium outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-recall-textMuted">상세 설명</label>
            <textarea
              rows={3}
              value={form.description || ""}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="업무 세부 내용이나 메모를 입력하세요."
              className="w-full resize-none rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text outline-none focus:border-recall-accent leading-relaxed"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-semibold text-recall-textMuted">진행 상태</label>
              <select
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value as TaskStatus })}
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text outline-none focus:border-recall-accent"
              >
                <option value="todo">{t.status_todo}</option>
                <option value="in_progress">{t.status_in_progress}</option>
                <option value="done">{t.status_done}</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-recall-textMuted">우선순위</label>
              <select
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value as TaskPriority })}
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text outline-none focus:border-recall-accent"
              >
                <option value="high">{t.priority_high}</option>
                <option value="medium">{t.priority_medium}</option>
                <option value="low">{t.priority_low}</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="relative" ref={assigneeRef}>
              <label className="mb-1 block text-xs font-semibold text-recall-textMuted">담당자</label>
              <input
                value={form.assignee || ""}
                onFocus={() => setIsAssigneeOpen(true)}
                onChange={(e) => {
                  setForm({ ...form, assignee: e.target.value });
                  setIsAssigneeOpen(true);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    setIsAssigneeOpen(false);
                  }
                }}
                placeholder="담당자 검색 또는 입력"
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs text-recall-text outline-none focus:border-recall-accent"
              />

              {isAssigneeOpen && filteredMembers.length > 0 && (
                <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-36 overflow-y-auto rounded-xl border border-recall-border bg-recall-bgSoft py-1 shadow-xl">
                  {filteredMembers.map((memberName) => (
                    <button
                      key={memberName}
                      type="button"
                      onClick={() => {
                        setForm({ ...form, assignee: memberName });
                        setIsAssigneeOpen(false);
                      }}
                      className="flex w-full items-center px-3 py-2 text-left text-xs hover:bg-white/5 transition"
                    >
                      <span>{memberName}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label className="mb-1 block text-xs font-semibold text-recall-textMuted">마감일</label>
              <div
                onClick={handleOpenDatePicker}
                className="relative w-full cursor-pointer rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-xs min-h-[34px] flex items-center justify-between hover:border-recall-accent transition"
              >
                <span className={form.deadline ? "text-recall-text" : "text-recall-textMuted"}>
                  {form.deadline || "마감일 선택"}
                </span>

                <CalendarIcon className="text-recall-textMuted flex-shrink-0" size={14} />

                <input
                  ref={dateInputRef}
                  type="date"
                  value={form.deadline || ""}
                  onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer pointer-events-auto"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-between items-center pt-5 border-t border-recall-border mt-4">
          <button
            type="button"
            onClick={() => {
              onDelete(task.id);
              onClose();
            }}
            className="flex items-center gap-1 rounded-lg border border-recall-danger/40 px-3 py-1.5 text-xs text-recall-danger hover:bg-recall-danger/10 transition"
          >
            <TrashIcon size={13} />
            {t.task_delete}
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-recall-border px-3.5 py-1.5 text-xs text-recall-textMuted hover:bg-white/5 transition"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="rounded-lg bg-recall-accent px-4 py-1.5 text-xs text-white font-medium hover:opacity-90 transition"
            >
              저장
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function InsertionGap({ id }: { id: string }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <div
      ref={(element) => setNodeRef(element)}
      className="transition-all"
      style={{ height: isOver ? "10px" : "6px", margin: isOver ? "0" : "-3px 0" }}
    >
      <div className={`h-full rounded-full transition-colors ${isOver ? "bg-recall-accent" : ""}`} />
    </div>
  );
}

function DraggableCard({
  task,
  onStatusChange,
  onSelectDetail,
  t,
}: {
  task: Task;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onSelectDetail: (task: Task) => void;
  t: any;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: task.id });
  const isDone = task.status === "done";
  const overdue = isOverdue(task.deadline) && !isDone;

  const priorityLabel: Record<TaskPriority, string> = {
    high: t.priority_high,
    medium: t.priority_medium,
    low: t.priority_low,
  };

  const style = transform
    ? { transform: `translate(${transform.x}px, ${transform.y}px)`, zIndex: 50 }
    : undefined;

  function handleToggleDone(e: React.MouseEvent) {
    e.stopPropagation();
    onStatusChange(task.id, task.status === "done" ? "todo" : "done");
  }

  return (
    <div
      ref={(element) => setNodeRef(element)}
      style={style}
      {...listeners}
      {...attributes}
      onClick={() => onSelectDetail(task)}
      className={`relative cursor-grab rounded-xl border p-3 transition active:cursor-grabbing ${
        isDragging
          ? "opacity-40 shadow-xl"
          : isDone
          ? "border-recall-border bg-recall-bg"
          : overdue
          ? "border-recall-danger/60 bg-recall-bgSoft hover:border-recall-danger"
          : "border-recall-border bg-recall-bgSoft hover:border-recall-accent/50"
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onPointerDown={(e) => e.stopPropagation()}
            onClick={handleToggleDone}
            aria-label={isDone ? "Undo complete" : "Mark as complete"}
            className={`flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded border transition-colors ${
              isDone ? "border-recall-border" : "border-recall-textMuted hover:border-recall-text"
            }`}
          >
            {isDone && <CheckIcon size={9} className="text-recall-textMuted" />}
          </button>

          <div className="flex items-center gap-1.5">
            <span
              className={`h-2 w-2 flex-shrink-0 rounded-full ${priorityDotClass[task.priority]} ${
                isDone ? "opacity-40" : ""
              }`}
            />
            <span className="text-xs text-recall-textMuted">{priorityLabel[task.priority]}</span>
          </div>

          {overdue && (
            <span className="flex items-center gap-1 rounded-full bg-recall-danger/15 px-2 py-0.5 text-[10px] font-semibold text-recall-danger">
              <WarningIcon size={10} className="flex-shrink-0" />
              지연
            </span>
          )}
        </div>
      </div>

      <p
        className={`mb-3 text-xs font-medium leading-relaxed ${
          isDone ? "text-recall-textMuted line-through" : "text-recall-text"
        }`}
      >
        {task.task}
      </p>

      <div className="flex items-center justify-between">
        <span className="text-xs text-recall-textMuted">{task.assignee ?? "-"}</span>
        <span className={`text-xs ${overdue ? "font-semibold text-recall-danger" : "text-recall-textMuted"}`}>
          {formatDeadline(task.deadline)}
        </span>
      </div>
    </div>
  );
}

function DroppableColumn({ col, children }: { col: any; children: React.ReactNode }) {
  const { isOver, setNodeRef } = useDroppable({ id: col.id });
  return (
    <div
      ref={(element) => setNodeRef(element)}
      className={`flex min-h-24 flex-col rounded-xl transition-colors ${isOver ? "bg-recall-accent/5" : ""}`}
    >
      {children}
    </div>
  );
}

export default function TaskBoard({
  taskList,
  workspaceId,
  onOpenModal,
  onStatusChange,
  onPriorityChange,
  onUpdateTask,
  onDelete,
  t,
}: Props) {
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [detailTask, setDetailTask] = useState<Task | null>(null);

  const [sortMode, setSortMode] = useState<SortMode>("deadline");
  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const sortMenuRef = useRef<HTMLDivElement>(null);

  const lang = t.settings_lang === "언어" ? "ko" : "en";

  const columns: { id: TaskStatus; title: string; barColorClass: string }[] = [
    { id: "todo", title: t.status_todo, barColorClass: "bg-recall-textMuted" },
    { id: "in_progress", title: t.status_in_progress, barColorClass: "bg-amber-400" },
    { id: "done", title: t.status_done, barColorClass: "bg-emerald-400" },
  ];

  const sortOptions: { value: SortMode; label: string }[] = [
    { value: "deadline", label: lang === "ko" ? "마감일순" : "By Deadline" },
    { value: "priority", label: lang === "ko" ? "중요도순" : "By Priority" },
    { value: "custom", label: lang === "ko" ? "사용자 지정" : "Custom Order" },
  ];

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (sortMenuRef.current && !sortMenuRef.current.contains(e.target as Node)) setSortMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const sortFn = sortMode === "deadline" ? sortByDeadline : sortMode === "priority" ? sortByPriority : null;

  const columnsWithTasks = columns.map((col) => {
    const colTasks = taskList.filter((t) => t.status === col.id);
    const sorted = sortFn ? sortFn(colTasks) : sortByCustomOrder(colTasks, loadCustomOrder(col.id));
    return { ...col, tasks: sorted };
  });

  function handleDragStart(event: DragStartEvent) {
    const task = taskList.find((t) => t.id === event.active.id);
    if (task) setActiveTask(task);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    setActiveTask(null);
    if (!over) return;

    const taskId = active.id as string;
    const overId = over.id as string;
    const task = taskList.find((t) => t.id === taskId);
    if (!task || !overId.startsWith("gap:")) return;

    const [, columnId, indexStr] = overId.split(":");
    const insertIndex = parseInt(indexStr, 10);
    const newStatus = columnId as TaskStatus;

    if (task.status !== newStatus) {
      onStatusChange(taskId, newStatus);
    }

    const currentCol = columnsWithTasks.find((c) => c.id === newStatus);
    const baseOrder = currentCol ? currentCol.tasks.map((t) => t.id) : loadCustomOrder(newStatus);
    const withoutMoved = baseOrder.filter((id) => id !== taskId);
    const clampedIndex = Math.max(0, Math.min(insertIndex, withoutMoved.length));
    const newOrder = [...withoutMoved.slice(0, clampedIndex), taskId, ...withoutMoved.slice(clampedIndex)];

    saveCustomOrder(newStatus, newOrder);
    setSortMode("custom");
  }

  function handleSaveTaskDetail(updatedTask: Task) {
    if (onUpdateTask) {
      onUpdateTask(updatedTask);
    } else {
      if (updatedTask.status !== detailTask?.status) {
        onStatusChange(updatedTask.id, updatedTask.status);
      }
      if (updatedTask.priority !== detailTask?.priority) {
        onPriorityChange(updatedTask.id, updatedTask.priority);
      }
    }
  }

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <div className="relative" ref={sortMenuRef}>
          <button
            onClick={() => setSortMenuOpen((v) => !v)}
            className="flex items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-textMuted hover:bg-white/5"
          >
            {sortOptions.find((o) => o.value === sortMode)?.label}
            <ChevronDownIcon size={12} className={sortMenuOpen ? "rotate-180" : ""} />
          </button>

          {sortMenuOpen && (
            <div className="absolute right-0 top-full z-30 mt-1 w-32 overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft py-1 shadow-lg">
              {sortOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    setSortMode(opt.value);
                    setSortMenuOpen(false);
                  }}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-xs text-recall-text hover:bg-white/5"
                >
                  {opt.label}
                  {sortMode === opt.value && <CheckIcon size={11} className="text-recall-accent" />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-3 gap-4">
          {columnsWithTasks.map((col) => (
            <div key={col.id} className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <div className={`h-3.5 w-[3px] rounded-sm ${col.barColorClass}`} />
                  <span className="text-xs font-medium text-recall-textMuted">{col.title}</span>
                  <span className="text-xs text-recall-textMuted">{col.tasks.length}</span>
                </div>
                <button
                  onClick={() => onOpenModal(col.id)}
                  className="flex h-5 w-5 items-center justify-center rounded hover:bg-white/5"
                >
                  <PlusIcon size={13} className="text-recall-textMuted" />
                </button>
              </div>

              <DroppableColumn col={col}>
                <InsertionGap id={`gap:${col.id}:0`} />
                {col.tasks.map((task, i) => (
                  <div key={task.id}>
                    <DraggableCard
                      task={task}
                      onStatusChange={onStatusChange}
                      onSelectDetail={(t) => setDetailTask(t)}
                      t={t}
                    />
                    <InsertionGap id={`gap:${col.id}:${i + 1}`} />
                  </div>
                ))}

                <button
                  onClick={() => onOpenModal(col.id)}
                  className="mt-2 w-full rounded-xl border border-dashed border-recall-border py-2 text-xs text-recall-textMuted hover:border-recall-accent hover:text-recall-accent"
                >
                  {t.task_add_btn}
                </button>
              </DroppableColumn>
            </div>
          ))}
        </div>

        <DragOverlay>
          {activeTask && (
            <div className="w-52 rounded-xl border border-recall-accent bg-recall-bgSoft p-3 opacity-95 shadow-xl">
              <p className="text-xs font-medium text-recall-text">{activeTask.task}</p>
              <div className="mt-2 flex items-center justify-between">
                <span className="text-xs text-recall-textMuted">{activeTask.assignee ?? "-"}</span>
                <span className="text-xs text-recall-textMuted">{formatDeadline(activeTask.deadline)}</span>
              </div>
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {detailTask && (
        <TaskDetailModal
          task={detailTask}
          workspaceId={workspaceId}
          onClose={() => setDetailTask(null)}
          onSave={handleSaveTaskDetail}
          onDelete={onDelete}
          t={t}
        />
      )}
    </div>
  );
}