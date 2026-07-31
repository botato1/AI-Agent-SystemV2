// src/components/DashboardView.tsx
import { useState } from "react";
import { Task, TaskPriority, TaskStatus } from "../types";
import { Contradiction, ContradictionStatus, ContradictionResolutionType } from "../services/contradiction";
import { useContradictions } from "../hooks/useContradictions";
import { useClampCheck } from "../hooks/useClampCheck";
import { WarningIcon, ChevronDownIcon } from "./icons";
import TaskBoard from "./TaskBoard";
import CreateTaskModal from "./CreateTaskmodal";
import ContradictionMessage from "./ContradictionMessage";
import ChangeSummaryModal from "./ChangeSummaryModal";

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

function severityBadge(severity: Contradiction["severity"], t: any) {
  const map = {
    high: { label: t.priority_high, className: "bg-recall-danger/15 text-recall-danger" },
    medium: { label: t.priority_medium, className: "bg-amber-500/15 text-amber-400" },
    low: { label: t.priority_low, className: "bg-recall-textMuted/15 text-recall-textMuted" },
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

function ContradictionLogCard({
  c,
  isExpanded,
  onToggleExpand,
  onDismiss,
  onResolve,
  t,
}: {
  c: Contradiction;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onDismiss: () => void;
  onResolve: (resolutionType: ContradictionResolutionType) => void;
  t: any;
}) {
  // 접힌 상태에서 실제로 텍스트가 잘리는지 측정해서, 잘릴 때만 "자세히 보기"를 보여준다
  // (짧은 내용에서 눌러도 아무 변화가 없는 버튼을 없애기 위함)
  const [clampRef, isClamped] = useClampCheck([c.id]);

  return (
    <div className="rounded-lg border border-recall-border bg-recall-bg p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-base font-bold text-recall-text">
          <WarningIcon size={15} className="text-recall-danger" />
          {t.contradiction_title}
        </span>
        <span className="text-sm text-recall-textMuted">{formatDate(c.detected_at)}</span>
      </div>

      <span className="mb-2 inline-block rounded-md bg-recall-bgMain px-1.5 py-1 text-xs font-medium text-recall-textMuted">
        {c.source_type === "meeting_segment" ? t.contradiction_source_meeting : t.contradiction_source_chat}
      </span>

      <div ref={clampRef}>
        <ContradictionMessage contradiction={c} expanded={isExpanded} t={t} />

        {c.reason && (
          <div className="mb-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
              {t.contradiction_reason_label}
            </p>
            <p data-clamp className={`text-base text-recall-textMuted ${isExpanded ? "" : "line-clamp-1"}`}>{c.reason}</p>
          </div>
        )}
      </div>

      {isClamped && (
        <button
          onClick={onToggleExpand}
          className="mb-2 flex items-center gap-1 text-sm font-medium text-recall-accent hover:underline"
        >
          {isExpanded ? t.contradiction_show_less : t.contradiction_show_more}
          <ChevronDownIcon size={13} className={`transition-transform ${isExpanded ? "rotate-180" : ""}`} />
        </button>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {severityBadge(c.severity, t)}
          <span className="text-sm text-recall-textMuted">
            {t.contradiction_confidence} {Math.round(c.confidence_score * 100)}%
          </span>
        </div>

        {c.status === "unresolved" && (
          <div className="flex gap-1.5">
            <button
              onClick={onDismiss}
              className="rounded-lg border border-recall-border px-2.5 py-1 text-sm text-recall-textMuted hover:bg-white/5"
            >
              {t.contradiction_dismiss}
            </button>
            <button
              onClick={() => onResolve("keep_reference")}
              className="rounded-lg border border-recall-border px-2.5 py-1 text-sm text-recall-text hover:bg-white/5"
            >
              {t.contradiction_keep}
            </button>
            <button
              onClick={() => onResolve("change_acknowledged")}
              className="rounded-lg bg-recall-accent px-2.5 py-1 text-sm font-medium text-white hover:opacity-90"
            >
              {t.contradiction_apply}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ContradictionLog({ workspaceId, t }: { workspaceId: string; t: any }) {
  const {
    statusFilter,
    setStatusFilter,
    contradictions,
    isLoading,
    resolve,
    dismiss,
    pendingSummaryFor,
    changeSummary,
    isChangeSummaryLoading,
    closeChangeSummary,
  } = useContradictions(workspaceId);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  function toggleExpanded(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const tabs: { key: ContradictionStatus; label: string }[] = [
    { key: "unresolved", label: t.contradiction_status_unresolved },
    { key: "resolved", label: t.contradiction_status_resolved },
    { key: "dismissed", label: t.contradiction_status_dismissed },
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
        <p className="text-base text-recall-textMuted">{t.common_loading}</p>
      ) : contradictions.length === 0 ? (
        <p className="text-base text-recall-textMuted">{t.contradiction_log_empty}</p>
      ) : (
        <div className="space-y-3">
          {contradictions.map((c) => (
            <ContradictionLogCard
              key={c.id}
              c={c}
              isExpanded={expandedIds.has(c.id)}
              onToggleExpand={() => toggleExpanded(c.id)}
              onDismiss={() => dismiss(c.id)}
              onResolve={(resolutionType) => resolve(c.id, resolutionType)}
              t={t}
            />
          ))}
        </div>
      )}

      {pendingSummaryFor && (
        <ChangeSummaryModal
          contradiction={pendingSummaryFor}
          changeSummary={changeSummary}
          isLoading={isChangeSummaryLoading}
          onClose={closeChangeSummary}
          t={t}
        />
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
          <ContradictionLog workspaceId={workspaceId} t={t} />
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