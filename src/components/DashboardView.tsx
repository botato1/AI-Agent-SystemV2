// src/components/DashboardView.tsx
import { useEffect, useRef, useState } from "react";
import { Task, TaskPriority, TaskStatus } from "../types";
import { WorkspaceDecision } from "../services/decision";
import { useWorkspaceDecisions } from "../hooks/useWorkspaceDecisions";
import { ChevronDownIcon } from "./icons";
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
  // 모순 카드의 "결정 참조" 배지를 눌러서 들어온 경우, 그 결정사항을 결정사항 탭에서
  // 바로 펼쳐 보여주기 위한 값 - 소비하고 나면 상위(App)에서 null로 리셋해줘야 한다.
  initialDecisionId?: string | null;
  onInitialDecisionIdConsumed?: () => void;
  t: any;
}

type DashboardTab = "tasks" | "decisions";

function formatShortDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function isWithinLastWeek(iso: string): boolean {
  const decidedAt = new Date(iso).getTime();
  return Date.now() - decidedAt <= 7 * 24 * 60 * 60 * 1000;
}

// 결정사항 하나 - 접었을 땐 현재 값만, 누르면 이 주제가 어떻게 바뀌어왔는지(history) 펼쳐서 보여준다.
// autoExpand는 모순 카드의 "결정 참조" 배지를 눌러서 들어왔을 때만 true - 펼친 채로 스크롤해서 보여준다.
function DecisionCard({ d, t, autoExpand }: { d: WorkspaceDecision; t: any; autoExpand?: boolean }) {
  const [isExpanded, setIsExpanded] = useState(!!autoExpand);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoExpand) cardRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [autoExpand]);

  return (
    <div
      ref={cardRef}
      className={`rounded-xl border p-4 transition-colors ${
        autoExpand ? "border-recall-accent bg-recall-accent/5" : "border-recall-border bg-recall-bg"
      }`}
    >
      <button
        onClick={() => setIsExpanded((v) => !v)}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="min-w-0">
          <p className="font-medium text-recall-text">{d.title}</p>
          <p className="mt-1 text-sm text-recall-textMuted">{d.decision_text}</p>
        </div>
        <span className="flex flex-shrink-0 items-center gap-1 text-sm text-recall-textMuted">
          {formatShortDate(d.decided_at)}
          <ChevronDownIcon size={13} className={`transition-transform ${isExpanded ? "rotate-180" : ""}`} />
        </span>
      </button>

      {isExpanded && d.history.length > 0 && (
        <div className="mt-4 space-y-2.5 border-t border-recall-border pt-4">
          {d.history
            .slice()
            .reverse()
            .map((h, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <span
                  className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${
                    h.status === "active" ? "bg-emerald-400" : "bg-recall-textMuted/40"
                  }`}
                />
                <span className="flex-shrink-0 text-recall-textMuted">{formatShortDate(h.decided_at)}</span>
                <span className="min-w-0 flex-1 truncate text-recall-text">{h.value}</span>
                {h.status === "active" && (
                  <span className="flex-shrink-0 rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-xs text-emerald-400">
                    {t.decisions_current_badge}
                  </span>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function DecisionsTab({
  workspaceId,
  tasks,
  t,
  focusDecisionId,
}: {
  workspaceId: string;
  tasks: Task[];
  t: any;
  focusDecisionId?: string | null;
}) {
  const { decisions, isLoading } = useWorkspaceDecisions(workspaceId);

  const inProgressCount = tasks.filter((task) => task.status === "in_progress").length;
  const changedThisWeekCount = decisions.filter((d) => isWithinLastWeek(d.decided_at)).length;

  const stats: { label: string; value: number }[] = [
    { label: t.decisions_stat_active, value: decisions.length },
    { label: t.decisions_stat_in_progress_tasks, value: inProgressCount },
    { label: t.decisions_stat_changed_this_week, value: changedThisWeekCount },
  ];

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-3 gap-3">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-xl border border-recall-border bg-recall-bg p-4">
            <p className="text-sm text-recall-textMuted">{stat.label}</p>
            <p className="mt-1.5 text-2xl font-bold text-recall-text">
              {stat.value}
              <span className="ml-0.5 text-base font-medium text-recall-textMuted">{t.decisions_count_unit}</span>
            </p>
          </div>
        ))}
      </div>

      <div>
        <div className="mb-3 flex items-baseline justify-between">
          <p className="text-sm font-semibold uppercase tracking-wide text-recall-textMuted">
            {t.decisions_list_title}
          </p>
          <p className="text-xs text-recall-textMuted">{t.decisions_list_hint}</p>
        </div>

        {isLoading ? (
          <p className="text-base text-recall-textMuted">{t.common_loading}</p>
        ) : decisions.length === 0 ? (
          <p className="text-base text-recall-textMuted">{t.decisions_empty}</p>
        ) : (
          <div className="space-y-3">
            {decisions.map((d) => (
              <DecisionCard key={d.id} d={d} t={t} autoExpand={d.id === focusDecisionId} />
            ))}
          </div>
        )}
      </div>
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
  initialDecisionId,
  onInitialDecisionIdConsumed,
  t,
}: DashboardViewProps) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("decisions");
  const [createInitialStatus, setCreateInitialStatus] = useState<TaskStatus | null>(null);
  const [focusDecisionId, setFocusDecisionId] = useState<string | null>(null);

  useEffect(() => {
    if (!initialDecisionId) return;
    setFocusDecisionId(initialDecisionId);
    setActiveTab("decisions");
    onInitialDecisionIdConsumed?.();
  }, [initialDecisionId]);

  const tabs: { id: DashboardTab; label: string }[] = [
    { id: "decisions", label: t.dashboard_tab_decisions },
    { id: "tasks", label: t.dashboard_tab_tasks },
  ];

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain p-6">
      <div className="mb-5 flex gap-1 border-b border-recall-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3.5 py-2 text-base ${
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
          <DecisionsTab workspaceId={workspaceId} tasks={tasks} t={t} focusDecisionId={focusDecisionId} />
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