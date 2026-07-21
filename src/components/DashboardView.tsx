import { useState } from "react";
import { ContradictionLogEntry, Task, TaskPriority, TaskStatus } from "../types";
import { WarningIcon } from "./icons";
import TaskBoard from "./TaskBoard";
import CreateTaskModal from "./CreateTaskmodal";

interface DashboardViewProps {
  userName: string;
  tasks: Task[];
  onCreateTask: (task: Omit<Task, "id">) => void;
  onStatusChange: (taskId: string, newStatus: TaskStatus) => void;
  onPriorityChange: (taskId: string, newPriority: TaskPriority) => void;
  onDeleteTask: (id: string) => void;
  contradictionLog: ContradictionLogEntry[];
  t: any; // App.tsx에서 주입되는 번역 객체
}

type DashboardTab = "tasks" | "log";

function statusBadge(status: ContradictionLogEntry["status"], t: any) {
  if (status === "pending") {
    return (
      <span className="rounded-full bg-recall-danger/15 px-2 py-0.5 text-[11px] text-recall-danger">
        {t.dashboard_contradiction_pending}
      </span>
    );
  }
  if (status === "kept") {
    return (
      <span className="rounded-full bg-recall-border px-2 py-0.5 text-[11px] text-recall-textMuted">
        {t.dashboard_contradiction_kept}
      </span>
    );
  }
  return (
    <span className="rounded-full bg-recall-accent/15 px-2 py-0.5 text-[11px] text-recall-accent">
      {t.dashboard_contradiction_changed}
    </span>
  );
}

// 모순 감지 로그 - 채널/회의 전반에서 감지된 모순 이력
function ContradictionLogList({ log, t }: { log: ContradictionLogEntry[]; t: any }) {
  return (
    <div className="space-y-2">
      {log.length === 0 ? (
        <p className="text-sm text-recall-textMuted">{t.dashboard_no_contradiction}</p>
      ) : (
        log.map((entry) => (
          <div key={entry.id} className="rounded-lg border border-recall-border p-3">
            <div className="mb-1 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-medium text-recall-textMuted">
                <WarningIcon size={12} className="text-recall-danger" />
                {entry.channelName}
              </span>
              <span className="text-[11px] text-recall-textMuted">{entry.date}</span>
            </div>
            <p className="mb-1.5 text-sm text-recall-text">{entry.description}</p>
            {statusBadge(entry.status, t)}
          </div>
        ))
      )}
    </div>
  );
}

export default function DashboardView({
  userName,
  tasks,
  onCreateTask,
  onStatusChange,
  onPriorityChange,
  onDeleteTask,
  contradictionLog,
  t,
}: DashboardViewProps) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("tasks");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const tabs: { id: DashboardTab; label: string }[] = [
    { id: "tasks", label: t.dashboard_tab_tasks },
    { id: "log", label: t.dashboard_tab_log },
  ];

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain p-4">
      {/* 사용자 그리팅 메시지 및 보조 멘트 영역이 완전히 제거되어 콘텐츠가 상단부터 시작합니다 */}
      <div className="mb-3 flex gap-0.5 border-b border-recall-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 text-sm ${
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
            onOpenModal={() => setShowCreateModal(true)}
            onStatusChange={onStatusChange}
            onPriorityChange={onPriorityChange}
            onDelete={onDeleteTask}
            t={t}
          />
        ) : (
          <ContradictionLogList log={contradictionLog} t={t} />
        )}
      </div>

      {showCreateModal && (
        <CreateTaskModal onClose={() => setShowCreateModal(false)} onCreate={onCreateTask}
        t={t} />
      )}
    </div>
  );
}