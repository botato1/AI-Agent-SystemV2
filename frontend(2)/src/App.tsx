// src/App.tsx
import { useState, useEffect } from "react";
import Sidebar, { PlaceholderKey } from "./components/Sidebar";
import MainArea from "./components/MainArea";
import VoiceMeetingView from "./components/VoiceMeetingView";
import DashboardView from "./components/DashboardView";
import DocumentAnalysisView from "./components/DocumentAnalysisView";
import GraphView from "./components/GraphView";
import Settings from "./components/Settings";
import ProfileModal from "./components/ProfileModal";
import AuthView from "./components/AuthView";
import { Channel, ContradictionLogEntry, Task, TaskPriority, TaskStatus, User, Workspace } from "./types";
import { useTheme } from "./hooks/useTheme";
import { useVoiceMeetings } from "./hooks/useVoiceMeetings";
import { useDocumentAnalysis } from "./hooks/useDocumentAnalysis";
import { Language, translations } from "./data/translations";
import { getMockData } from "./data/mockData"; // 구조화된 목업 가져오기

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
  const [lang, setLang] = useState<Language>("ko");
  const t = translations[lang];
  
  // 현재 언어셋에 맞는 목업 데이터 미리 가져오기
  const initialData = getMockData(lang);

  // 로그인/회원가입 상태
  const [registeredAccounts, setRegisteredAccounts] = useState<RegisteredAccount[]>([]);
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  // 워크스페이스 목록 관리
  const [workspaces, setWorkspaces] = useState<Workspace[]>(initialData.mockWorkspaces);
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState(initialData.mockWorkspaces[0].id);

  // 채팅방/할일/로그 등 목업 데이터 상태 분배
  const [channelsByWorkspace, setChannelsByWorkspace] = useState<Record<string, Channel[]>>({
    [initialData.mockWorkspaces[0].id]: initialData.mockChannels,
  });
  const [tasksByWorkspace, setTasksByWorkspace] = useState<Record<string, Task[]>>({
    [initialData.mockWorkspaces[0].id]: initialData.mockTasks,
  });
  const [contradictionLogByWorkspace, setContradictionLogByWorkspace] = useState<
    Record<string, ContradictionLogEntry[]>
  >({
    [initialData.mockWorkspaces[0].id]: initialData.mockContradictionLog,
  });

  // 언어가 변경될 때 독립된 함수로부터 새로운 언어 목업 세트를 할당받아 에러 완치
  useEffect(() => {
    const data = getMockData(lang);
    const defaultWsId = data.mockWorkspaces[0].id;

    setWorkspaces(data.mockWorkspaces);
    setCurrentWorkspaceId(defaultWsId);
    setChannelsByWorkspace({
      [defaultWsId]: data.mockChannels,
    });
    setTasksByWorkspace({
      [defaultWsId]: data.mockTasks,
    });
    setContradictionLogByWorkspace({
      [defaultWsId]: data.mockContradictionLog,
    });
    setSelection({
      type: "channel",
      channel: data.mockChannels[0],
    });
  }, [lang]);

  const channels = channelsByWorkspace[currentWorkspaceId] ?? [];
  const tasks = tasksByWorkspace[currentWorkspaceId] ?? [];
  const contradictionLog = contradictionLogByWorkspace[currentWorkspaceId] ?? [];

  const [selection, setSelection] = useState<Selection>({
    type: "channel",
    channel: initialData.mockChannels[0],
  });
  
  const [showProfile, setShowProfile] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const { theme, toggleTheme } = useTheme();

  const voiceMeetings = useVoiceMeetings(currentWorkspaceId, lang);
  const hasRecording = voiceMeetings.meetings.some((m) => m.status === "recording");
  const hasPaused = voiceMeetings.meetings.some((m) => m.status === "paused");
  const voiceMeetingStatus = hasRecording ? "recording" : hasPaused ? "paused" : null;

  const documentAnalysis = useDocumentAnalysis(currentWorkspaceId);
  const activeRecorderName = voiceMeetings.meetings.find((m) => m.status === "recording")?.startedBy ?? null;

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
      [currentWorkspaceId]: (prev[currentWorkspaceId] ?? []).map((tItem) =>
        tItem.id === id ? { ...tItem, status: newStatus } : tItem
      ),
    }));
  }

  function handleTaskPriorityChange(id: string, newPriority: TaskPriority) {
    setTasksByWorkspace((prev) => ({
      ...prev,
      [currentWorkspaceId]: (prev[currentWorkspaceId] ?? []).map((tItem) =>
        tItem.id === id ? { ...tItem, priority: newPriority } : tItem
      ),
    }));
  }

  function handleDeleteTask(id: string) {
    setTasksByWorkspace((prev) => ({
      ...prev,
      [currentWorkspaceId]: (prev[currentWorkspaceId] ?? []).filter((tItem) => tItem.id !== id),
    }));
  }

  function handleCreateWorkspace() {
    const newWorkspace: Workspace = {
      id: crypto.randomUUID(),
      name: `${t.name_new_workspace}${workspaces.length + 1}`,
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
      name: `${t.name_new_chatroom}${channels.length + 1}`,
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
    setSelection((prev) =>
      prev.type === "channel" && prev.channel.id === id
        ? { type: "channel", channel: { ...prev.channel, name } }
        : prev
    );
  }

  function handleDeleteChannel(id: string) {
    setChannelsByWorkspace((prev) => {
      const next = (prev[currentWorkspaceId] ?? []).filter((c) => c.id !== id);
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
        lang={lang}
        t={t}
      />

      {selection.type === "channel" ? (
        <MainArea channel={selection.channel} activeRecorderName={activeRecorderName} t={t} />
      ) : selection.key === "voiceMeeting" ? (
        <VoiceMeetingView {...voiceMeetings} t={t} />
      ) : selection.key === "dashboard" ? (
        <DashboardView
          userName={currentUser.name}
          tasks={tasks}
          onCreateTask={handleCreateTask}
          onStatusChange={handleTaskStatusChange}
          onPriorityChange={handleTaskPriorityChange}
          onDeleteTask={handleDeleteTask}
          contradictionLog={contradictionLog}
          t={t}
        />
      ) : selection.key === "docAnalysis" ? (
        <DocumentAnalysisView {...documentAnalysis} t={t} />
      ) : selection.key === "graph" ? (
        <GraphView
          documents={documentAnalysis.documents}
          onGoToAnalysis={(id) => {
            documentAnalysis.selectDocument(id);
            setSelection({ type: "placeholder", key: "docAnalysis" });
          }}
          t={t}
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
          t={t}
        />
      )}
      {showSettings && (
        <Settings
          onClose={() => setShowSettings(false)}
          theme={theme}
          onToggleTheme={toggleTheme}
          lang={lang}
          onChangeLang={setLang}
          t={t}
        />
      )}
    </div>
  );
}