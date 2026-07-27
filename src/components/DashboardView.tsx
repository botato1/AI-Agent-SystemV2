// src/components/DashboardView.tsx
import { useState } from "react";
import { Task, TaskPriority, TaskStatus } from "../types";
import { Contradiction, ContradictionStatus } from "../services/contradiction";
import { useContradictions } from "../hooks/useContradictions";
import { WarningIcon } from "./icons";
import TaskBoard from "./TaskBoard";
import CreateTaskModal from "./CreateTaskmodal";

interface DashboardViewProps {
  workspaceId: string;
  userName: string;
  tasks: Task[];
  onCreateTask: (task: Omit<Task, "id">) => void;
  onUpdateTask?: (updatedTask: Task) => void;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onPriorityChange: (taskId: string, newPriority: TaskPriority) => void;
  onDeleteTask: (id: string) => void;
  t: any;
}

type DashboardTab = "tasks" | "log";

function severityBadge(severity: Contradiction["severity"]) {
  const map = {
    high: { label: "높음", className: "bg-recall-danger/15 text-recall-danger" },
    medium: { label: "중간", className: "bg-amber-500/15 text-amber-400" },
    low: { label: "낮음", className: "bg-recall-textMuted/15 text-recall-textMuted" },
  } as const;
  const { label, className } = map[severity];
  return <span className={`rounded-full px-2 py-0.5 text-xs ${className}`}>{label}</span>;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

function ContradictionLog({ workspaceId }: { workspaceId: string }) {
  const {
    statusFilter,
    setStatusFilter,
    contradictions,
    isLoading,
    resolve,
    dismiss,
  } = useContradictions(workspaceId);

  const tabs: { key: ContradictionStatus; label: string }[] = [
    { key: "unresolved", label: "미해결" },
    { key: "resolved", label: "해결됨" },
    { key: "dismissed", label: "무시됨" },
  ];

  return (
    <div>
      <div className="mb-3 flex gap-0.5">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setStatusFilter(tab.key)}
            className={`rounded-lg px-2.5 py-1 text-sm ${
              statusFilter === tab.key
                ? "bg-recall-accent/15 text-recall-accent"
                : "text-recall-textMuted hover:bg-white/5"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-base text-recall-textMuted">불러오는 중...</p>
      ) : contradictions.length === 0 ? (
        <p className="text-base text-recall-textMuted">표시할 항목이 없습니다.</p>
      ) : (
        <div className="space-y-2">
          {contradictions.map((c) => (
            <div key={c.id} className="rounded-lg border border-recall-border p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-sm font-medium text-recall-textMuted">
                  <WarningIcon size={12} className="text-recall-danger" />
                  {c.source_type === "meeting_segment" ? "회의 발언" : "채팅 메시지"}
                </span>
                <span className="text-xs text-recall-textMuted">{formatDate(c.detected_at)}</span>
              </div>

              <div className="mb-1.5 space-y-1 text-base">
                <p className="text-recall-text">
                  <span className="text-recall-textMuted">발언: </span>
                  {c.statement_text_snapshot}
                </p>
                <p className="text-recall-text">
                  <span className="text-recall-textMuted">기준자료: </span>
                  {c.reference_text_snapshot}
                </p>
              </div>

              {c.reason && <p className="mb-2 text-sm text-recall-textMuted">{c.reason}</p>}

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  {severityBadge(c.severity)}
                  <span className="text-xs text-recall-textMuted">
                    신뢰도 {Math.round(c.confidence_score * 100)}%
                  </span>
                </div>

                {c.status === "unresolved" && (
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => dismiss(c.id)}
                      className="rounded-lg border border-recall-border px-2.5 py-1 text-sm text-recall-textMuted hover:bg-white/5"
                    >
                      무시
                    </button>
                    <button
                      onClick={() => resolve(c.id, "keep_reference")}
                      className="rounded-lg border border-recall-border px-2.5 py-1 text-sm text-recall-text hover:bg-white/5"
                    >
                      기준 유지
                    </button>
                    <button
                      onClick={() => resolve(c.id, "change_acknowledged")}
                      className="rounded-lg bg-recall-accent px-2.5 py-1 text-sm font-medium text-white hover:opacity-90"
                    >
                      변경 인지
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DashboardView({
  workspaceId,
  userName,
  tasks,
  onCreateTask,
  onUpdateTask,
  onStatusChange,
  onPriorityChange,
  onDeleteTask,
  t,
}: DashboardViewProps) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("tasks");
  const [createInitialStatus, setCreateInitialStatus] = useState<TaskStatus | null>(null);

  const tabs: { id: DashboardTab; label: string }[] = [
    { id: "tasks", label: t.dashboard_tab_tasks },
    { id: "log", label: t.dashboard_tab_log },
  ];

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain p-4">
      <div className="mb-3 flex gap-0.5 border-b border-recall-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 text-base ${
              activeTab === tab.id
                ? "border-b-2 border-recall-accent text-recall-text"
                : "text-recall-textMuted hover:text-recall-text"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">
        {activeTab === "tasks" ? (
          <TaskBoard
            taskList={tasks}
            workspaceId={workspaceId}
            onOpenModal={(status) => setCreateInitialStatus(status || "todo")}
            onStatusChange={onStatusChange}
            onPriorityChange={onPriorityChange}
            onUpdateTask={onUpdateTask}
            onDelete={onDeleteTask}
            t={t}
          />
        ) : (
          <ContradictionLog workspaceId={workspaceId} />
        )}
      </div>

      {createInitialStatus && (
        <CreateTaskModal
          workspaceId={workspaceId}
          initialStatus={createInitialStatus}
          onClose={() => setCreateInitialStatus(null)}
          onCreate={onCreateTask}
          t={t}
        />
      )}
    </div>
  );
}