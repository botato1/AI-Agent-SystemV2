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
}

type DashboardTab = "tasks" | "log";

function todayGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "좋은 아침이에요";
  if (hour < 18) return "오늘도 화이팅이에요";
  return "오늘 하루도 고생 많았어요";
}

function statusBadge(status: ContradictionLogEntry["status"]) {
  if (status === "pending") {
    return (
      <span className="rounded-full bg-recall-danger/15 px-2 py-0.5 text-[11px] text-recall-danger">
        확인 필요
      </span>
    );
  }
  if (status === "kept") {
    return (
      <span className="rounded-full bg-recall-border px-2 py-0.5 text-[11px] text-recall-textMuted">
        기존 유지됨
      </span>
    );
  }
  return (
    <span className="rounded-full bg-recall-accent/15 px-2 py-0.5 text-[11px] text-recall-accent">
      변경됨
    </span>
  );
}

// 모순 감지 로그 - 채널/회의 전반에서 감지된 모순 이력
function ContradictionLogList({ log }: { log: ContradictionLogEntry[] }) {
  return (
    <div className="space-y-2">
      {log.length === 0 ? (
        <p className="text-sm text-recall-textMuted">아직 감지된 모순이 없어요.</p>
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
            {statusBadge(entry.status)}
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
}: DashboardViewProps) {
  const [activeTab, setActiveTab] = useState<DashboardTab>("tasks");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const tabs: { id: DashboardTab; label: string }[] = [
    { id: "tasks", label: "할일" },
    { id: "log", label: "로그" },
  ];

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain p-4">
      <div className="mb-4">
        <p className="text-lg font-semibold text-recall-text">
          {todayGreeting()}, {userName}님
        </p>
        <p className="text-sm text-recall-textMuted">오늘도 당신의 업무를 스마트하게 도와드릴게요.</p>
      </div>

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
          />
        ) : (
          <ContradictionLogList log={contradictionLog} />
        )}
      </div>

      {showCreateModal && (
        <CreateTaskModal onClose={() => setShowCreateModal(false)} onCreate={onCreateTask} />
      )}
    </div>
  );
}