import { useState } from "react";
import Sidebar, { PlaceholderKey } from "./components/Sidebar";
import MainArea from "./components/MainArea";
import VoiceMeetingView from "./components/VoiceMeetingView";
import DashboardView from "./components/DashboardView";
import DocumentAnalysisView from "./components/DocumentAnalysisView";
import GraphView from "./components/GraphView";
import Settings from "./components/Settings";
import ProfileModal from "./components/ProfileModal";
import AuthView from "./components/AuthView";
import { mockChannels, mockTasks, mockContradictionLog, mockWorkspaces } from "./data/mockData";
import { Channel, ContradictionLogEntry, Task, TaskPriority, TaskStatus, User, Workspace } from "./types";
import { useTheme } from "./hooks/useTheme";
import { useVoiceMeetings } from "./hooks/useVoiceMeetings";
import { useDocumentAnalysis } from "./hooks/useDocumentAnalysis";

type Selection = { type: "channel"; channel: Channel } | { type: "placeholder"; key: PlaceholderKey };

interface RegisteredAccount {
  username: string;
  password: string;
  user: User;
}

const PLACEHOLDER_LABELS: Record<
  Exclude<PlaceholderKey, "voiceMeeting" | "dashboard" | "docAnalysis" | "graph">,
  string
> = {};

export default function App() {
  // 로그인/회원가입 - 실제 백엔드 없이 브라우저 메모리에만 저장 (새로고침하면 초기화됨)
  const [registeredAccounts, setRegisteredAccounts] = useState<RegisteredAccount[]>([]);
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  // 워크스페이스 목록 - 생성/이름변경/전환 가능
  const [workspaces, setWorkspaces] = useState<Workspace[]>(mockWorkspaces);
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState(mockWorkspaces[0].id);

  // 채팅방/할일을 워크스페이스 id별로 분리 저장 - 워크스페이스를 바꿔도 서로 안 섞이게 함
  const [channelsByWorkspace, setChannelsByWorkspace] = useState<Record<string, Channel[]>>({
    [mockWorkspaces[0].id]: mockChannels,
  });
  const [tasksByWorkspace, setTasksByWorkspace] = useState<Record<string, Task[]>>({
    [mockWorkspaces[0].id]: mockTasks,
  });
  const [contradictionLogByWorkspace, setContradictionLogByWorkspace] = useState<
    Record<string, ContradictionLogEntry[]>
  >({
    [mockWorkspaces[0].id]: mockContradictionLog,
  });
  const channels = channelsByWorkspace[currentWorkspaceId] ?? [];
  const tasks = tasksByWorkspace[currentWorkspaceId] ?? [];
  const contradictionLog = contradictionLogByWorkspace[currentWorkspaceId] ?? [];

  const [selection, setSelection] = useState<Selection>({
    type: "channel",
    channel: mockChannels[0],
  });
  const [showProfile, setShowProfile] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const { theme, toggleTheme } = useTheme();

  // 음성 회의/문서 분석 상태도 워크스페이스 id 기준으로 분리됨 (각 훅 내부에서 처리)
  const voiceMeetings = useVoiceMeetings(currentWorkspaceId);
  const hasRecording = voiceMeetings.meetings.some((m) => m.status === "recording");
  const hasPaused = voiceMeetings.meetings.some((m) => m.status === "paused");
  const voiceMeetingStatus = hasRecording ? "recording" : hasPaused ? "paused" : null;

  const documentAnalysis = useDocumentAnalysis(currentWorkspaceId);

  // 지금 녹음 중인 회의가 있으면 "누가 시작했는지" 이름을 뽑아서 채팅방 참여자 아바타에 표시
  const activeRecorderName = voiceMeetings.meetings.find((m) => m.status === "recording")?.startedBy ?? null;

  // 아직 로그인 안 했으면 로그인/회원가입 화면만 보여줌
  if (!currentUser) {
    return (
      <AuthView
        registeredAccounts={registeredAccounts}
        onSignUp={(account) => {
          setRegisteredAccounts((prev) => [...prev, account]);
          setCurrentUser(account.user);
        }}
        onLogIn={(user) => setCurrentUser(user)}
      />
    );
  }

  function handleChangeAvatarColor(color: string) {
    setCurrentUser((prev) => (prev ? { ...prev, avatarColor: color, avatarImageUrl: null } : prev));
    setRegisteredAccounts((prev) =>
      prev.map((a) =>
        a.user.username === currentUser?.username
          ? { ...a, user: { ...a.user, avatarColor: color, avatarImageUrl: null } }
          : a
      )
    );
  }

  function handleChangeAvatarImage(imageUrl: string) {
    setCurrentUser((prev) => (prev ? { ...prev, avatarImageUrl: imageUrl } : prev));
    setRegisteredAccounts((prev) =>
      prev.map((a) =>
        a.user.username === currentUser?.username ? { ...a, user: { ...a.user, avatarImageUrl: imageUrl } } : a
      )
    );
  }

  function handleLogout() {
    setCurrentUser(null);
  }

  function handleCreateTask(task: Omit<Task, "id">) {
    setTasksByWorkspace((prev) => ({
      ...prev,
      [currentWorkspaceId]: [...(prev[currentWorkspaceId] ?? []), { ...task, id: crypto.randomUUID() }],
    }));
  }

  function handleTaskStatusChange(id: string, newStatus: TaskStatus) {
    setTasksByWorkspace((prev) => ({
      ...prev,
      [currentWorkspaceId]: (prev[currentWorkspaceId] ?? []).map((t) =>
        t.id === id ? { ...t, status: newStatus } : t
      ),
    }));
  }

  function handleTaskPriorityChange(id: string, newPriority: TaskPriority) {
    setTasksByWorkspace((prev) => ({
      ...prev,
      [currentWorkspaceId]: (prev[currentWorkspaceId] ?? []).map((t) =>
        t.id === id ? { ...t, priority: newPriority } : t
      ),
    }));
  }

  function handleDeleteTask(id: string) {
    setTasksByWorkspace((prev) => ({
      ...prev,
      [currentWorkspaceId]: (prev[currentWorkspaceId] ?? []).filter((t) => t.id !== id),
    }));
  }

  // 새 워크스페이스는 채널/할일이 하나도 없는 빈 상태로 시작 - 전환하면 대시보드로 이동
  function handleCreateWorkspace() {
    const newWorkspace: Workspace = {
      id: crypto.randomUUID(),
      name: `워크스페이스 ${workspaces.length + 1}`,
    };
    setWorkspaces((prev) => [...prev, newWorkspace]);
    setChannelsByWorkspace((prev) => ({ ...prev, [newWorkspace.id]: [] }));
    setTasksByWorkspace((prev) => ({ ...prev, [newWorkspace.id]: [] }));
    setContradictionLogByWorkspace((prev) => ({ ...prev, [newWorkspace.id]: [] }));
    setCurrentWorkspaceId(newWorkspace.id);
    setSelection({ type: "placeholder", key: "dashboard" });
  }

  function handleRenameWorkspace(id: string, name: string) {
    setWorkspaces((prev) => prev.map((w) => (w.id === id ? { ...w, name } : w)));
  }

  // 워크스페이스 전환 - 지금 보고 있던 채널은 다른 워크스페이스 것일 수 있으니
  // 새 워크스페이스의 첫 채널로(없으면 대시보드로) 화면을 옮겨줌
  function handleSelectWorkspace(id: string) {
    setCurrentWorkspaceId(id);
    const nextChannels = channelsByWorkspace[id] ?? [];
    setSelection(
      nextChannels.length > 0
        ? { type: "channel", channel: nextChannels[0] }
        : { type: "placeholder", key: "dashboard" }
    );
  }

  function handleCreateChannel() {
    const newChannel: Channel = {
      id: crypto.randomUUID(),
      name: `채팅방 ${channels.length + 1}`,
    };
    setChannelsByWorkspace((prev) => ({
      ...prev,
      [currentWorkspaceId]: [...(prev[currentWorkspaceId] ?? []), newChannel],
    }));
    setSelection({ type: "channel", channel: newChannel });
  }

  function handleRenameChannel(id: string, name: string) {
    setChannelsByWorkspace((prev) => ({
      ...prev,
      [currentWorkspaceId]: (prev[currentWorkspaceId] ?? []).map((c) => (c.id === id ? { ...c, name } : c)),
    }));
    // 지금 보고 있는 채널이 이름 바뀐 채널이면 selection도 최신 이름으로 갱신
    setSelection((prev) =>
      prev.type === "channel" && prev.channel.id === id
        ? { type: "channel", channel: { ...prev.channel, name } }
        : prev
    );
  }

  function handleDeleteChannel(id: string) {
    setChannelsByWorkspace((prev) => {
      const next = (prev[currentWorkspaceId] ?? []).filter((c) => c.id !== id);
      // 지금 보고 있던 채널이 삭제된 채널이면, 남은 채널 중 첫 번째로 이동 (없으면 대시보드로)
      setSelection((sel) => {
        if (sel.type === "channel" && sel.channel.id === id) {
          return next.length > 0
            ? { type: "channel", channel: next[0] }
            : { type: "placeholder", key: "dashboard" };
        }
        return sel;
      });
      return { ...prev, [currentWorkspaceId]: next };
    });
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar
        workspaces={workspaces}
        currentWorkspaceId={currentWorkspaceId}
        onSelectWorkspace={handleSelectWorkspace}
        onCreateWorkspace={handleCreateWorkspace}
        onRenameWorkspace={handleRenameWorkspace}
        channels={channels}
        selectedChannelId={selection.type === "channel" ? selection.channel.id : null}
        activePlaceholder={selection.type === "placeholder" ? selection.key : null}
        voiceMeetingStatus={voiceMeetingStatus}
        onSelectChannel={(channel) => setSelection({ type: "channel", channel })}
        onSelectPlaceholder={(key) => setSelection({ type: "placeholder", key })}
        onCreateChannel={handleCreateChannel}
        onRenameChannel={handleRenameChannel}
        onDeleteChannel={handleDeleteChannel}
        user={currentUser}
        onOpenProfile={() => setShowProfile(true)}
        onOpenSettings={() => setShowSettings(true)}
        onLogout={handleLogout}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {selection.type === "channel" ? (
        <MainArea channel={selection.channel} activeRecorderName={activeRecorderName} />
      ) : selection.key === "voiceMeeting" ? (
        <VoiceMeetingView {...voiceMeetings} />
      ) : selection.key === "dashboard" ? (
        <DashboardView
          userName={currentUser.name}
          tasks={tasks}
          onCreateTask={handleCreateTask}
          onStatusChange={handleTaskStatusChange}
          onPriorityChange={handleTaskPriorityChange}
          onDeleteTask={handleDeleteTask}
          contradictionLog={contradictionLog}
        />
      ) : selection.key === "docAnalysis" ? (
        <DocumentAnalysisView {...documentAnalysis} />
      ) : selection.key === "graph" ? (
        <GraphView
          documents={documentAnalysis.documents}
          onGoToAnalysis={(id) => {
            documentAnalysis.selectDocument(id);
            setSelection({ type: "placeholder", key: "docAnalysis" });
          }}
        />
      ) : (
        <div className="flex h-full flex-1 items-center justify-center bg-recall-bgMain">
          <p className="text-sm text-recall-textMuted">
            "{PLACEHOLDER_LABELS[selection.key]}" 화면은 아직 준비 중이에요.
          </p>
        </div>
      )}

      {showProfile && (
        <ProfileModal
          user={currentUser}
          onClose={() => setShowProfile(false)}
          onChangeAvatarColor={handleChangeAvatarColor}
          onChangeAvatarImage={handleChangeAvatarImage}
        />
      )}
      {showSettings && (
        <Settings onClose={() => setShowSettings(false)} theme={theme} onToggleTheme={toggleTheme} />
      )}
    </div>
  );
}