// src/components/DashboardView.tsx
import { useEffect, useRef, useState } from "react";
import { Task, TaskPriority, TaskStatus } from "../types";
import { Category } from "../services/category";
import { WorkspaceDecision } from "../services/decision";
import { useWorkspaceDecisions } from "../hooks/useWorkspaceDecisions";
import { ChevronDownIcon } from "./icons";
import TaskBoard from "./TaskBoard";
import CreateTaskModal from "./CreateTaskmodal";

interface DashboardViewProps {
  workspaceId: string;
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
  // 결정사항 카드에서 "관련 회의록 보기"를 눌렀을 때 App 레벨의 결정 미리보기 모달을 연다
  // (모순 카드의 "결정 참조"와 동일한 모달을 재사용 - 사유 + 원본 회의로 이동 버튼 포함).
  onOpenDecision: (decisionId: string) => void;
  categories: Category[];
  selectedCategoryId: string | null;
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
function DecisionCard({
  d,
  t,
  autoExpand,
  onOpenDecision,
}: {
  d: WorkspaceDecision;
  t: any;
  autoExpand?: boolean;
  onOpenDecision: (decisionId: string) => void;
}) {
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
        {/* 결정 내용(decision_text)은 시간이 지나면서 바뀐 문구라 여기 그대로 반복해서
            보여주면 제목이랑 겹쳐 보인다 - 기본 화면엔 제목만 남기고, 실제 문구는 펼쳤을 때
            나오는 변경 이력(history) 목록에서 각 시점별로 보여준다. */}
        <p className="min-w-0 truncate font-medium text-recall-text">{d.title}</p>
        <span className="flex flex-shrink-0 items-center gap-1 text-sm text-recall-textMuted">
          {formatShortDate(d.decided_at)}
          <ChevronDownIcon size={13} className={`transition-transform ${isExpanded ? "rotate-180" : ""}`} />
        </span>
      </button>

      {/* 사유는 기본 화면엔 안 보이고, 펼친 이력 목록의 각 항목 안에서만 보여준다
          (카드에도 있고 팝업에도 있어서 같은 걸 두 번 보여주던 문제 정리). */}
      {isExpanded && d.history.length > 0 && (
        <div className="mt-4 space-y-1 border-t border-recall-border pt-4">
          {d.history
            .slice()
            .reverse()
            .map((h, i) => (
              <button
                key={i}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenDecision(d.id);
                }}
                className="group block w-full rounded-lg px-1.5 py-1 text-left hover:bg-white/5"
              >
                <div className="flex items-center gap-2 text-sm">
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
                {/* 클릭하면 근거 팝업이 뜬다는 게 한눈에 안 보인다는 피드백 - 사유 부분만
                    호버 시 강조색으로 바뀌게 해서 "여기 누르면 뭔가 있다"는 걸 드러낸다. */}
                {h.reason && (
                  <p className="mt-0.5 truncate pl-3.5 text-xs text-recall-textMuted/60 group-hover:text-recall-accent group-hover:underline">
                    {t.decision_reason_label} {h.reason}
                  </p>
                )}
              </button>
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
  onOpenDecision,
}: {
  workspaceId: string;
  tasks: Task[];
  t: any;
  focusDecisionId?: string | null;
  onOpenDecision: (decisionId: string) => void;
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
              <DecisionCard
                key={d.id}
                d={d}
                t={t}
                autoExpand={d.id === focusDecisionId}
                onOpenDecision={onOpenDecision}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardView({
  workspaceId,
  tasks,
  onCreateTask,
  onUpdateTask,
  onStatusChange,
  onPriorityChange,
  onDeleteTask,
  initialDecisionId,
  onInitialDecisionIdConsumed,
  onOpenDecision,
  categories,
  selectedCategoryId,
  t,
}: DashboardViewProps) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("decisions");
  // 사이드바 전역 카테고리 선택기 - null("전체")이면 전부, 아니면 그 카테고리 할 일만.
  const visibleTasks = selectedCategoryId ? tasks.filter((t) => t.category_id === selectedCategoryId) : tasks;
  function handleCreateTask(input: Omit<Task, "id">) {
    onCreateTask(selectedCategoryId ? { ...input, category_id: selectedCategoryId } : input);
  }
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
            taskList={visibleTasks}
            workspaceId={workspaceId}
            categories={categories}
            onOpenModal={(status) => setCreateInitialStatus(status || "todo")}
            onStatusChange={onStatusChange}
            onPriorityChange={onPriorityChange}
            onUpdateTask={onUpdateTask}
            onDelete={onDeleteTask}
            t={t}
          />
        ) : (
          <DecisionsTab
            workspaceId={workspaceId}
            tasks={visibleTasks}
            t={t}
            focusDecisionId={focusDecisionId}
            onOpenDecision={onOpenDecision}
          />
        )}
      </div>

      {createInitialStatus && (
        <CreateTaskModal
          workspaceId={workspaceId}
          initialStatus={createInitialStatus}
          onClose={() => setCreateInitialStatus(null)}
          onCreate={handleCreateTask}
          t={t}
        />
      )}
    </div>
  );
}