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
  MoreIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  TrashIcon,
} from "./icons";

interface Props {
  taskList: Task[];
  onOpenModal: () => void;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onPriorityChange: (taskId: string, newPriority: TaskPriority) => void;
  onDelete: (taskId: string) => void;
}

const priorityLabel: Record<TaskPriority, string> = { high: "높음", medium: "중간", low: "낮음" };

// 우선순위/상태는 accent 하나로만 표현하면 구분이 안 되니, 의미 있는 색(빨강/주황/초록)을 그대로 사용
const priorityDotClass: Record<TaskPriority, string> = {
  high: "bg-rose-400",
  medium: "bg-amber-400",
  low: "bg-emerald-400",
};

const columns: { id: TaskStatus; title: string; barColorClass: string }[] = [
  { id: "todo", title: "해야 할 일", barColorClass: "bg-recall-textMuted" },
  { id: "in_progress", title: "진행 중", barColorClass: "bg-amber-400" },
  { id: "done", title: "완료", barColorClass: "bg-emerald-400" },
  { id: "delayed", title: "지연", barColorClass: "bg-rose-400" },
];

const statusOptions: { value: TaskStatus; label: string }[] = [
  { value: "todo", label: "해야 할 일" },
  { value: "in_progress", label: "진행 중" },
  { value: "done", label: "완료" },
  { value: "delayed", label: "지연" },
];

const priorityOptions: { value: TaskPriority; label: string }[] = [
  { value: "high", label: "높음" },
  { value: "medium", label: "중간" },
  { value: "low", label: "낮음" },
];

const priorityWeight: Record<TaskPriority, number> = { high: 0, medium: 1, low: 2 };

type SortMode = "deadline" | "priority" | "custom";
const sortOptions: { value: SortMode; label: string }[] = [
  { value: "deadline", label: "마감일순" },
  { value: "priority", label: "중요도순" },
  { value: "custom", label: "사용자 지정" },
];

const CUSTOM_ORDER_KEY = "recall-task-custom-order";

function saveCustomOrder(columnId: string, taskIds: string[]) {
  try {
    const all = JSON.parse(localStorage.getItem(CUSTOM_ORDER_KEY) ?? "{}");
    all[columnId] = taskIds;
    localStorage.setItem(CUSTOM_ORDER_KEY, JSON.stringify(all));
  } catch {
    /* 무시 - 정렬 저장 실패해도 기능엔 지장 없음 */
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

function sortByDeadline(tasks: Task[]): Task[] {
  return [...tasks].sort((a, b) => {
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

type DropdownView = "main" | "status" | "priority" | "delete";

function TaskDropdown({
  task,
  onStatusChange,
  onPriorityChange,
  onDelete,
  onClose,
}: {
  task: Task;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onPriorityChange: (taskId: string, newPriority: TaskPriority) => void;
  onDelete: (taskId: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<DropdownView>("main");

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute right-0 top-6 z-20 w-40 overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft py-1 shadow-lg"
    >
      {view === "main" && (
        <>
          <button
            onClick={() => setView("status")}
            className="flex w-full items-center justify-between px-3 py-2 text-xs text-recall-textMuted hover:bg-white/5"
          >
            상태
            <ChevronDownIcon size={11} className="-rotate-90" />
          </button>
          <button
            onClick={() => setView("priority")}
            className="flex w-full items-center justify-between px-3 py-2 text-xs text-recall-textMuted hover:bg-white/5"
          >
            우선순위
            <ChevronDownIcon size={11} className="-rotate-90" />
          </button>
          <div className="my-1 border-t border-recall-border" />
          <button
            onClick={() => setView("delete")}
            className="flex w-full items-center gap-2 px-3 py-2 text-xs text-recall-danger hover:bg-white/5"
          >
            <TrashIcon size={13} />
            삭제
          </button>
        </>
      )}

      {view === "status" && (
        <>
          <button
            onClick={() => setView("main")}
            className="flex w-full items-center gap-1.5 border-b border-recall-border px-3 py-2 text-[11px] text-recall-textMuted hover:bg-white/5"
          >
            <ChevronLeftIcon size={11} />
            상태
          </button>
          {statusOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                onStatusChange(task.id, opt.value);
                onClose();
              }}
              className="flex w-full items-center justify-between px-3 py-2 text-xs text-left text-recall-text hover:bg-white/5"
            >
              {opt.label}
              {task.status === opt.value && <CheckIcon size={12} className="text-recall-accent" />}
            </button>
          ))}
        </>
      )}

      {view === "priority" && (
        <>
          <button
            onClick={() => setView("main")}
            className="flex w-full items-center gap-1.5 border-b border-recall-border px-3 py-2 text-[11px] text-recall-textMuted hover:bg-white/5"
          >
            <ChevronLeftIcon size={11} />
            우선순위
          </button>
          {priorityOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => {
                onPriorityChange(task.id, opt.value);
                onClose();
              }}
              className="flex w-full items-center justify-between px-3 py-2 text-xs text-left text-recall-text hover:bg-white/5"
            >
              {opt.label}
              {task.priority === opt.value && <CheckIcon size={12} className="text-recall-accent" />}
            </button>
          ))}
        </>
      )}

      {view === "delete" && (
        <div className="p-3">
          <p className="mb-3 text-xs leading-relaxed text-recall-text">이 업무를 삭제할까요?</p>
          <div className="flex gap-2">
            <button
              onClick={() => setView("main")}
              className="flex-1 rounded-lg border border-recall-border py-1.5 text-xs text-recall-textMuted hover:bg-white/5"
            >
              취소
            </button>
            <button
              onClick={() => {
                onDelete(task.id);
                onClose();
              }}
              className="flex-1 rounded-lg bg-recall-danger py-1.5 text-xs text-white"
            >
              삭제
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// 카드와 카드 사이 삽입 지점 - 평소엔 얇은 줄, 드래그 중인 카드가 위에 오면 강조색으로 확장
function InsertionGap({ id }: { id: string }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <div
      ref={setNodeRef}
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
  onPriorityChange,
  onDelete,
}: {
  task: Task;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onPriorityChange: (taskId: string, newPriority: TaskPriority) => void;
  onDelete: (taskId: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: task.id });
  const [openDropdown, setOpenDropdown] = useState(false);
  const isDone = task.status === "done";

  const style = transform
    ? { transform: `translate(${transform.x}px, ${transform.y}px)`, zIndex: 50 }
    : undefined;

  function handleToggleDone() {
    onStatusChange(task.id, task.status === "done" ? "todo" : "done");
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      className={`relative cursor-grab rounded-xl border p-3 transition active:cursor-grabbing ${
        isDragging
          ? "opacity-40 shadow-xl"
          : isDone
          ? "border-recall-border bg-recall-bg"
          : "border-recall-border bg-recall-bgSoft hover:border-recall-accent/50"
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onPointerDown={(e) => e.stopPropagation()}
            onClick={handleToggleDone}
            aria-label={isDone ? "완료 취소" : "완료 처리"}
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
        </div>

        <div className="relative" onPointerDown={(e) => e.stopPropagation()}>
          <button
            onClick={() => setOpenDropdown((v) => !v)}
            className="flex h-5 w-5 items-center justify-center rounded hover:bg-white/5"
          >
            <MoreIcon size={13} className="text-recall-textMuted" />
          </button>
          {openDropdown && (
            <TaskDropdown
              task={task}
              onStatusChange={onStatusChange}
              onPriorityChange={onPriorityChange}
              onDelete={onDelete}
              onClose={() => setOpenDropdown(false)}
            />
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
        <span className="text-xs text-recall-textMuted">{formatDeadline(task.deadline)}</span>
      </div>
    </div>
  );
}

function DroppableColumn({ col, children }: { col: (typeof columns)[0]; children: React.ReactNode }) {
  const { isOver, setNodeRef } = useDroppable({ id: col.id });
  return (
    <div
      ref={setNodeRef}
      className={`flex min-h-24 flex-col rounded-xl transition-colors ${isOver ? "bg-recall-accent/5" : ""}`}
    >
      {children}
    </div>
  );
}

export default function TaskBoard({ taskList, onOpenModal, onStatusChange, onPriorityChange, onDelete }: Props) {
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("deadline");
  const [sortMenuOpen, setSortMenuOpen] = useState(false);
  const sortMenuRef = useRef<HTMLDivElement>(null);

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
        <div className="grid grid-cols-4 gap-4">
          {columnsWithTasks.map((col) => (
            <div key={col.id} className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <div className={`h-3.5 w-[3px] rounded-sm ${col.barColorClass}`} />
                  <span className="text-xs font-medium text-recall-textMuted">{col.title}</span>
                  <span className="text-xs text-recall-textMuted">{col.tasks.length}</span>
                </div>
                <button
                  onClick={onOpenModal}
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
                      onPriorityChange={onPriorityChange}
                      onDelete={onDelete}
                    />
                    <InsertionGap id={`gap:${col.id}:${i + 1}`} />
                  </div>
                ))}

                <button
                  onClick={onOpenModal}
                  className="mt-2 w-full rounded-xl border border-dashed border-recall-border py-2 text-xs text-recall-textMuted hover:border-recall-accent hover:text-recall-accent"
                >
                  + 업무 추가
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
    </div>
  );
}