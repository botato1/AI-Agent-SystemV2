import React, { useState, useEffect } from "react";
import Sidebar, { PlaceholderKey } from "./components/Sidebar";
import MainArea from "./components/MainArea";
import VoiceMeetingView from "./components/VoiceMeetingView";
import HomeView from "./components/HomeView";
import DashboardView from "./components/DashboardView";
import DocumentAnalysisView from "./components/DocumentAnalysisView";
import GraphView from "./components/GraphView";
import AiChatView from "./components/AiChatView";
import Settings from "./components/Settings";
import ProfileModal from "./components/ProfileModal";
import AuthView from "./components/AuthView";
import PasswordResetConfirmView from "./components/PasswordResetConfirmView";

import { Channel, User, Workspace } from "./types";
import { useTheme } from "./hooks/useTheme";
import { useLiveMeeting } from "./hooks/useLiveMeeting";
import { useDocumentAnalysis } from "./hooks/useDocumentAnalysis";
import { useRealTasks } from "./hooks/useRealTasks";
import { Language, translations } from "./data/translations";
import { hashAvatarColor, loadAvatarColor, saveAvatarColor } from "./data/avatarColors";
import {
  getProfileApi,
  logoutApi,
  uploadProfileImageApi,
  resolveAvatarUrl,
  deleteAccountApi,
  DeleteAccountResponse,
} from "./services/auth";
import {
  createWorkspaceApi,
  getWorkspaceListApi,
  updateWorkspaceApi,
  deleteWorkspaceApi,
  getWorkspaceMembersApi,
} from "./services/workspace";
import {
  getRoomListApi,
  createRoomApi,
  updateRoomApi,
  deleteRoomApi,
} from "./services/room";

interface RegisteredAccount {
  username: string;
  email?: string;
  password: string;
  user: User;
}

type Selection = { type: "channel"; channel: Channel } | { type: "placeholder"; key: PlaceholderKey };

const PLACEHOLDER_LABELS: Record<
  Exclude<PlaceholderKey, "home" | "voiceMeeting" | "dashboard" | "docAnalysis" | "graph" | "aiChat">,
  string
> = {};

export default function App() {
  const [lang, setLang] = useState<Language>("ko");
  const t = translations[lang];

  // 로그인/회원가입 상태
  const [registeredAccounts, setRegisteredAccounts] = useState<RegisteredAccount[]>([]);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [isAuthChecking, setIsAuthChecking] = useState(true);

  // 비밀번호 재설정 메일 링크(?token=...)로 들어온 경우, 로그인 여부와 무관하게
  // 새 비밀번호 설정 화면부터 보여준다.
  const [passwordResetToken, setPasswordResetToken] = useState<string | null>(() => {
    return new URLSearchParams(window.location.search).get("token");
  });

  // 💡 워크스페이스 목록 상태 (목업 중복 방지를 위해 빈 배열로 시작)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);

  // 선택된 워크스페이스 ID
  const [currentWorkspaceId, setCurrentWorkspaceId] = useState<string>(() => {
    return localStorage.getItem("last_workspace_id") || "";
  });

  // 워크스페이스 멤버 id → 표시 이름 매핑 (채팅 메시지 발신자 이름 표시용)
  const [memberNameById, setMemberNameById] = useState<Record<string, string>>({});
  // 워크스페이스 멤버 id → 프로필 이미지 URL 매핑 (채팅 메시지 발신자 아바타 표시용)
  const [memberAvatarById, setMemberAvatarById] = useState<Record<string, string | null>>({});

  // 채팅방별 데이터 상태
  const [channelsByWorkspace, setChannelsByWorkspace] = useState<Record<string, Channel[]>>({});

  const [selection, setSelection] = useState<Selection>({
    type: "placeholder",
    key: "home",
  });

  const [showProfile, setShowProfile] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const { theme, toggleTheme } = useTheme();

  // 1. 자동 로그인 체크
  useEffect(() => {
    async function checkAutoLogin() {
      const token = localStorage.getItem("access_token");
      if (!token) {
        setIsAuthChecking(false);
        return;
      }

      const profileResult = await getProfileApi();

      if (profileResult.status === "success" && profileResult.user) {
        const fixedAvatarColor =
          loadAvatarColor(profileResult.user.username) || hashAvatarColor(profileResult.user.username);
        saveAvatarColor(profileResult.user.username, fixedAvatarColor);

        setCurrentUser({
          id: profileResult.user.id,
          name: profileResult.user.display_name || profileResult.user.username,
          username: profileResult.user.username,
          status: "online",
          avatarColor: fixedAvatarColor,
          avatarImageUrl: resolveAvatarUrl(profileResult.user.profile_image_url),
        });
      } else {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      }

      setIsAuthChecking(false);
    }

    checkAutoLogin();
  }, []);

  // 2. 백엔드 워크스페이스 실시간 목록 조회 및 동기화
  useEffect(() => {
    async function loadRealWorkspaces() {
      if (!currentUser) return;

      const res = await getWorkspaceListApi();

      if (res.status === "success" && res.workspaces.length > 0) {
        setWorkspaces(res.workspaces);

        const savedWsId = localStorage.getItem("last_workspace_id");
        const exists = res.workspaces.find((w) => w.id === savedWsId);

        const targetWsId = exists && savedWsId ? savedWsId : res.workspaces[0].id;
        setCurrentWorkspaceId(targetWsId);
        localStorage.setItem("last_workspace_id", targetWsId);
      }
    }

    loadRealWorkspaces();
  }, [currentUser]);

  // 2-1. 워크스페이스 선택/전환 시 실시간 채팅방(rooms) 목록 조회
  useEffect(() => {
    async function loadRooms() {
      if (!currentWorkspaceId) return;

      const res = await getRoomListApi(currentWorkspaceId);

      if (res.status === "success") {
        setChannelsByWorkspace((prev) => ({
          ...prev,
          [currentWorkspaceId]: res.rooms.map((r) => ({ id: r.id, name: r.name })),
        }));
      }
    }

    loadRooms();
  }, [currentWorkspaceId]);

  // 2-2. 워크스페이스 선택/전환 시 멤버 목록 조회 (채팅 메시지 발신자 이름 표시용)
  useEffect(() => {
    async function loadMembers() {
      if (!currentWorkspaceId) {
        setMemberNameById({});
        setMemberAvatarById({});
        return;
      }

      const res = await getWorkspaceMembersApi(currentWorkspaceId);

      if (res.status === "success") {
        const nextNameMap: Record<string, string> = {};
        const nextAvatarMap: Record<string, string | null> = {};
        res.members.forEach((m) => {
          const userId = m.user_id || m.id;
          if (userId) {
            nextNameMap[userId] = m.display_name || m.username;
            nextAvatarMap[userId] = resolveAvatarUrl(m.profile_image_url);
          }
        });
        setMemberNameById(nextNameMap);
        setMemberAvatarById(nextAvatarMap);
      }
    }

    loadMembers();
  }, [currentWorkspaceId]);

  // 💡 현재 선택된 워크스페이스 객체 추출
  const currentWorkspace = workspaces.find((w) => w.id === currentWorkspaceId) || null;

  const channels = channelsByWorkspace[currentWorkspaceId] ?? [];

  const liveMeeting = useLiveMeeting(currentWorkspaceId, {
    id: currentUser?.id ?? "",
    name: currentUser?.name ?? "",
  });
  const voiceMeetingStatus =
    liveMeeting.status === "recording" ? "recording" : liveMeeting.status === "paused" ? "paused" : null;

  const documentAnalysis = useDocumentAnalysis(currentWorkspaceId);
  const activeRecorderName = voiceMeetingStatus ? liveMeeting.startedByName : null;

  const realTasks = useRealTasks(currentWorkspaceId, memberNameById);

  // 회원가입
  const handleSignUp = (account: RegisteredAccount) => {
    setRegisteredAccounts((prev) => [...prev, account]);
  };

  // 로그인
  const handleLogIn = (user: User) => {
    setCurrentUser(user);
  };

  // 로그아웃 (상태 및 워크스페이스 완전 초기화)
  const handleLogOut = async () => {
    await logoutApi();
    localStorage.removeItem("last_workspace_id");
    localStorage.removeItem("recall-task-custom-order");
    setWorkspaces([]);
    setCurrentUser(null);

    setCurrentWorkspaceId("");
    setSelection({ type: "placeholder", key: "home" });
    setChannelsByWorkspace({});
    setMemberNameById({});
  };

  // 회원 탈퇴 (성공 시에만 로그아웃과 동일하게 상태 초기화)
  const handleDeleteAccount = async (password: string): Promise<DeleteAccountResponse> => {
    const res = await deleteAccountApi(password);
    if (res.status === "success") {
      localStorage.removeItem("last_workspace_id");
      setWorkspaces([]);
      setCurrentUser(null);
      setCurrentWorkspaceId("");
      setSelection({ type: "placeholder", key: "home" });
      setChannelsByWorkspace({});
      setMemberNameById({});
    }
    return res;
  };

  function handleChangeAvatarColor(color: string) {
    setCurrentUser((prev) => {
      if (!prev) return prev;
      saveAvatarColor(prev.username, color);
      return { ...prev, avatarColor: color, avatarImageUrl: null };
    });
  }

  async function handleChangeAvatarImage(file: File) {
    const previewUrl = URL.createObjectURL(file);
    setCurrentUser((prev) => (prev ? { ...prev, avatarImageUrl: previewUrl } : prev));

    const res = await uploadProfileImageApi(file);
    if (res.status === "success" && res.user) {
      const resolvedUrl = resolveAvatarUrl(res.user.profile_image_url);
      setCurrentUser((prev) => (prev ? { ...prev, avatarImageUrl: resolvedUrl } : prev));
      if (currentUser) {
        setMemberAvatarById((prev) => ({ ...prev, [currentUser.id]: resolvedUrl }));
      }
    } else {
      alert(`프로필 이미지 변경 실패: ${res.message}`);
    }
  }

  // 워크스페이스 생성 API
  async function handleCreateWorkspace() {
    const wsName = `${t.name_new_workspace}${workspaces.length + 1}`;

    const apiRes = await createWorkspaceApi(wsName);

    if (apiRes.status === "success" && apiRes.workspace) {
      const newWorkspace = apiRes.workspace;

      setWorkspaces((prev) => [...prev, newWorkspace]);
      setChannelsByWorkspace((prev) => ({ ...prev, [newWorkspace.id]: [] }));

      setCurrentWorkspaceId(newWorkspace.id);
      localStorage.setItem("last_workspace_id", newWorkspace.id);
      setSelection({ type: "placeholder", key: "home" });
    } else {
      alert(`워크스페이스 생성 실패: ${apiRes.message}`);
    }
  }

  // 워크스페이스 이름 수정 API
  async function handleRenameWorkspace(id: string, name: string) {
    if (!name.trim()) return;

    const res = await updateWorkspaceApi(id, name);

    if (res.status === "success" && res.workspace) {
      const updatedName = res.workspace.name;
      setWorkspaces((prev) =>
        prev.map((w) => (w.id === id ? { ...w, name: updatedName } : w))
      );
    } else {
      alert(`워크스페이스 이름 변경 실패: ${res.message}`);
    }
  }

  // 워크스페이스 삭제 API
  async function handleDeleteWorkspace(id: string) {
    const res = await deleteWorkspaceApi(id);

    if (res.status === "success") {
      const nextWorkspaces = workspaces.filter((w) => w.id !== id);
      setWorkspaces(nextWorkspaces);

      if (currentWorkspaceId === id) {
        const nextWsId = nextWorkspaces.length > 0 ? nextWorkspaces[0].id : "";
        setCurrentWorkspaceId(nextWsId);
        if (nextWsId) {
          localStorage.setItem("last_workspace_id", nextWsId);
        } else {
          localStorage.removeItem("last_workspace_id");
        }
      }
    } else {
      alert(res.message);
    }
  }

  // 워크스페이스 선택
  function handleSelectWorkspace(id: string) {
    setCurrentWorkspaceId(id);
    localStorage.setItem("last_workspace_id", id);

    const nextChannels = channelsByWorkspace[id] ?? [];
    setSelection(
      nextChannels.length > 0
        ? { type: "channel", channel: nextChannels[0] }
        : { type: "placeholder", key: "home" }
    );
  }

  async function handleCreateChannel() {
    const newName = `${t.name_new_chatroom}${channels.length + 1}`;

    const res = await createRoomApi(currentWorkspaceId, newName);

    if (res.status === "success" && res.room) {
      const newChannel: Channel = { id: res.room.id, name: res.room.name };
      setChannelsByWorkspace((prev) => ({
        ...prev,
        [currentWorkspaceId]: [...(prev[currentWorkspaceId] ?? []), newChannel],
      }));
      setSelection({ type: "channel", channel: newChannel });
    } else {
      alert(`채팅방 생성 실패: ${res.message}`);
    }
  }

  async function handleRenameChannel(id: string, name: string) {
    if (!name.trim()) return;

    const res = await updateRoomApi(currentWorkspaceId, id, name);

    if (res.status === "success" && res.room) {
      const updatedName = res.room.name;
      setChannelsByWorkspace((prev) => ({
        ...prev,
        [currentWorkspaceId]: (prev[currentWorkspaceId] ?? []).map((c) =>
          c.id === id ? { ...c, name: updatedName } : c
        ),
      }));
      setSelection((prev) =>
        prev.type === "channel" && prev.channel.id === id
          ? { type: "channel", channel: { ...prev.channel, name: updatedName } }
          : prev
      );
    } else {
      alert(`채팅방 이름 변경 실패: ${res.message}`);
    }
  }

  async function handleDeleteChannel(id: string) {
    const res = await deleteRoomApi(currentWorkspaceId, id);

    if (res.status === "success") {
      setChannelsByWorkspace((prev) => {
        const next = (prev[currentWorkspaceId] ?? []).filter((c) => c.id !== id);
        setSelection((sel) => {
          if (sel.type === "channel" && sel.channel.id === id) {
            return next.length > 0
              ? { type: "channel", channel: next[0] }
              : { type: "placeholder", key: "home" };
          }
          return sel;
        });
        return { ...prev, [currentWorkspaceId]: next };
      });
    } else {
      alert(res.message);
    }
  }

  if (passwordResetToken) {
    return (
      <PasswordResetConfirmView
        resetToken={passwordResetToken}
        onSuccess={() => {
          window.history.replaceState(null, "", window.location.pathname);
          setPasswordResetToken(null);
        }}
      />
    );
  }

  if (isAuthChecking) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-recall-bg text-recall-textMuted text-base">
        로그인 정보를 확인 중입니다...
      </div>
    );
  }

  if (!currentUser) {
    return (
      <AuthView
        registeredAccounts={registeredAccounts}
        onSignUp={handleSignUp}
        onLogIn={handleLogIn}
      />
    );
  }

  return (
    <div key={currentUser.id} className="flex h-screen w-screen overflow-hidden">
      <Sidebar
        workspaces={workspaces}
        currentWorkspaceId={currentWorkspaceId}
        onSelectWorkspace={handleSelectWorkspace}
        onCreateWorkspace={handleCreateWorkspace}
        onRenameWorkspace={handleRenameWorkspace}
        onDeleteWorkspace={handleDeleteWorkspace}
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
        onLogout={handleLogOut}
        theme={theme}
        onToggleTheme={toggleTheme}
        lang={lang}
        t={t}
      />

      {selection.type === "channel" ? (
        <MainArea
          channel={selection.channel}
          workspaceId={currentWorkspaceId}
          currentUser={{
            id: currentUser.id,
            name: currentUser.name,
            avatarColor: currentUser.avatarColor,
            avatarImageUrl: currentUser.avatarImageUrl,
          }}
          memberNameById={memberNameById}
          memberAvatarById={memberAvatarById}
          activeRecorderName={activeRecorderName}
          t={t}
        />
      ) : selection.key === "home" ? (
        <HomeView
          workspaceId={currentWorkspaceId}
          userId={currentUser.id}
          userName={currentUser.name}
          onNavigate={(key) => setSelection({ type: "placeholder", key })}
          onBeginScheduledMeeting={(meetingId) => {
            liveMeeting.beginScheduled(meetingId);
            setSelection({ type: "placeholder", key: "voiceMeeting" });
          }}
          t={t}
        />
      ) : selection.key === "aiChat" ? (
        <AiChatView workspaceId={currentWorkspaceId} t={t} />
      ) : selection.key === "voiceMeeting" ? (
        <VoiceMeetingView
          workspaceId={currentWorkspaceId}
          status={liveMeeting.status}
          meeting={liveMeeting.meeting}
          segments={liveMeeting.segments}
          partial={liveMeeting.partial}
          contradictionAlerts={liveMeeting.contradictionAlerts}
          errorMessage={liveMeeting.errorMessage}
          onStart={liveMeeting.start}
          onPause={liveMeeting.pause}
          onResume={liveMeeting.resume}
          onStop={liveMeeting.stop}
          onReset={liveMeeting.reset}
          onMapLiveSpeakers={liveMeeting.mapSpeakerNames}
          onRenameLive={liveMeeting.renameMeeting}
          t={t}
        />
      ) : selection.key === "dashboard" ? (
        <DashboardView
          workspaceId={currentWorkspaceId}
          userName={currentUser.name}
          tasks={realTasks.tasks}
          onCreateTask={realTasks.createTask}
          onUpdateTask={realTasks.updateTask}
          onStatusChange={realTasks.changeStatus}
          onPriorityChange={realTasks.changePriority}
          onDeleteTask={realTasks.removeTask}
          t={t}
        />
      ) : selection.key === "docAnalysis" ? (
        <DocumentAnalysisView workspaceId={currentWorkspaceId} {...documentAnalysis} t={t} />
      ) : selection.key === "graph" ? (
        <GraphView
          workspaceId={currentWorkspaceId}
          documents={documentAnalysis.documents}
          t={t}
        />
      ) : (
        <div className="flex h-full flex-1 items-center justify-center bg-recall-bgMain">
          <p className="text-base text-recall-textMuted">
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
          onUpdateSuccess={(updatedUser) => setCurrentUser(updatedUser)}
          t={t}
        />
      )}

      {showSettings && (
        <Settings
          onClose={() => setShowSettings(false)}
          currentWorkspace={currentWorkspace}
          theme={theme}
          onToggleTheme={toggleTheme}
          lang={lang}
          onChangeLang={setLang}
          t={t}
          onLogout={handleLogOut}
          onDeleteAccount={handleDeleteAccount}
        />
      )}
    </div>
  );
}