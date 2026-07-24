import { useEffect, useRef, useState } from "react";
import { Channel, User, Workspace } from "../types";
import { Theme } from "../hooks/useTheme";
import ProfilePopup from "./ProfilePopup";
import InviteMemberModal from "./InviteMemberModal";
import ManageMembersModal from "./ManageMembersModal";
import {
  HomeIcon,
  ChatIcon,
  DocumentIcon,
  MicIcon,
  GraphIcon,
  PlusIcon,
  MoreIcon,
  PencilIcon,
  TrashIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CheckIcon,
} from "./icons";

export type PlaceholderKey = "dashboard" | "docAnalysis" | "voiceMeeting" | "graph";

interface SidebarProps {
  workspaces: Workspace[];
  currentWorkspaceId: string;
  onSelectWorkspace: (id: string) => void;
  onCreateWorkspace: () => void;
  onRenameWorkspace: (id: string, name: string) => void;
  onDeleteWorkspace?: (id: string) => void;
  channels: Channel[];
  selectedChannelId: string | null;
  activePlaceholder: PlaceholderKey | null;
  voiceMeetingStatus: "recording" | "paused" | null;
  onSelectChannel: (channel: Channel) => void;
  onSelectPlaceholder: (key: PlaceholderKey) => void;
  onCreateChannel: () => void;
  onRenameChannel: (id: string, name: string) => void;
  onDeleteChannel: (id: string) => void;
  user: User;
  onOpenProfile: () => void;
  onOpenSettings: () => void;
  onLogout: () => void;
  theme: Theme;
  onToggleTheme: () => void;
  lang: any;
  t: any;
}

export default function Sidebar({
  workspaces,
  currentWorkspaceId,
  onSelectWorkspace,
  onCreateWorkspace,
  onRenameWorkspace,
  onDeleteWorkspace,
  channels,
  selectedChannelId,
  activePlaceholder,
  voiceMeetingStatus,
  onSelectChannel,
  onSelectPlaceholder,
  onCreateChannel,
  onRenameChannel,
  onDeleteChannel,
  user,
  onOpenProfile,
  onOpenSettings,
  onLogout,
  theme,
  onToggleTheme,
  t,
}: SidebarProps) {
  const [isChannelsExpanded, setIsChannelsExpanded] = useState(true);
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [openMenuChannelId, setOpenMenuChannelId] = useState<string | null>(null);
  const prevChannelIdsRef = useRef<Set<string>>(new Set(channels.map((c) => c.id)));
  const prevWorkspaceIdForChannelsRef = useRef(currentWorkspaceId);

  // 워크스페이스 드롭다운 및 메뉴 관련 상태
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const [editingWorkspaceId, setEditingWorkspaceId] = useState<string | null>(null);
  const [workspaceDraftName, setWorkspaceDraftName] = useState("");
  const [openWsMenuId, setOpenWsMenuId] = useState<string | null>(null);

  // 초대 모달 및 팀원 관리 모달용 상태
  const [invitingWorkspace, setInvitingWorkspace] = useState<Workspace | null>(null);
  const [managingWorkspace, setManagingWorkspace] = useState<Workspace | null>(null);

  const workspaceMenuRef = useRef<HTMLDivElement>(null);
  const prevWorkspaceIdsRef = useRef<Set<string>>(new Set(workspaces.map((w) => w.id)));

  const currentWorkspace = workspaces.find((w) => w.id === currentWorkspaceId) ?? workspaces[0];

  const ANALYSIS_ITEMS: { key: PlaceholderKey; icon: typeof DocumentIcon; label: string }[] = [
    { key: "docAnalysis", icon: DocumentIcon, label: t.sidebar_doc_analysis },
    { key: "graph", icon: GraphIcon, label: t.sidebar_graph },
  ];

  useEffect(() => {
    const prevIds = prevWorkspaceIdsRef.current;
    const newOnes = workspaces.filter((w) => !prevIds.has(w.id));

    // 목록을 통째로 처음 불러온 경우(prevIds가 비어있음)는 제외하고,
    // 실제로 새로 생긴 워크스페이스가 정확히 1개일 때만 이름 입력 모드로 전환
    if (prevIds.size > 0 && newOnes.length === 1) {
      setEditingWorkspaceId(newOnes[0].id);
      setWorkspaceDraftName(newOnes[0].name);
    }

    prevWorkspaceIdsRef.current = new Set(workspaces.map((w) => w.id));
  }, [workspaces]);

  useEffect(() => {
    if (!isWorkspaceMenuOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (workspaceMenuRef.current && !workspaceMenuRef.current.contains(e.target as Node)) {
        setIsWorkspaceMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isWorkspaceMenuOpen]);

  useEffect(() => {
    if (!openWsMenuId) return;
    function handleClickOutside() {
      setOpenWsMenuId(null);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [openWsMenuId]);

  function startRenameWorkspace(workspace: Workspace) {
    setEditingWorkspaceId(workspace.id);
    setWorkspaceDraftName(workspace.name);
    setOpenWsMenuId(null);
  }

  function commitRenameWorkspace() {
    if (editingWorkspaceId && workspaceDraftName.trim()) {
      onRenameWorkspace(editingWorkspaceId, workspaceDraftName.trim());
    }
    setEditingWorkspaceId(null);
  }

  useEffect(() => {
    // 워크스페이스 자체가 바뀐 경우엔 채널 목록이 통째로 교체된 것이므로
    // "새로 생긴 채널"로 오인하지 않도록 이번 사이클은 추적 목록만 재동기화
    const sameWorkspace = prevWorkspaceIdForChannelsRef.current === currentWorkspaceId;

    if (sameWorkspace) {
      const prevIds = prevChannelIdsRef.current;
      const newOnes = channels.filter((c) => !prevIds.has(c.id));

      if (prevIds.size > 0 && newOnes.length === 1) {
        setEditingChannelId(newOnes[0].id);
        setDraftName(newOnes[0].name);
      }
    }

    prevChannelIdsRef.current = new Set(channels.map((c) => c.id));
    prevWorkspaceIdForChannelsRef.current = currentWorkspaceId;
  }, [channels, currentWorkspaceId]);

  useEffect(() => {
    if (!openMenuChannelId) return;
    function handleClickOutside() {
      setOpenMenuChannelId(null);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [openMenuChannelId]);

  function startRename(channel: Channel) {
    setEditingChannelId(channel.id);
    setDraftName(channel.name);
    setOpenMenuChannelId(null);
  }

  function commitRename() {
    if (editingChannelId && draftName.trim()) {
      onRenameChannel(editingChannelId, draftName.trim());
    }
    setEditingChannelId(null);
  }

  return (
    <div className="flex h-full w-64 flex-shrink-0 flex-col bg-recall-bg text-recall-text">
      {/* 1. 상단 워크스페이스 영역 */}
      <div ref={workspaceMenuRef} className="relative px-3 pb-3 pt-4">
        <button
          onClick={() => setIsWorkspaceMenuOpen((v) => !v)}
          className="flex w-full items-center justify-between rounded-lg px-1 py-1 text-left hover:bg-white/5"
        >
          <span className="truncate text-base font-semibold">{currentWorkspace?.name}</span>
          <ChevronDownIcon
            size={14}
            className={`flex-shrink-0 text-recall-textMuted transition-transform ${
              isWorkspaceMenuOpen ? "rotate-180" : ""
            }`}
          />
        </button>

        {isWorkspaceMenuOpen && (
          <div className="absolute left-3 right-3 top-full z-30 mt-1 rounded-lg border border-recall-border bg-recall-bgSoft p-1.5 shadow-lg">
            {workspaces.map((ws) => {
              const isEditing = editingWorkspaceId === ws.id;
              const isCurrent = ws.id === currentWorkspaceId;
              const isWsMenuOpen = openWsMenuId === ws.id;

              return (
                <div key={ws.id} className="group relative flex items-center">
                  {isEditing ? (
                    <input
                      autoFocus
                      value={workspaceDraftName}
                      onChange={(e) => setWorkspaceDraftName(e.target.value)}
                      onFocus={(e) => e.target.select()}
                      onBlur={commitRenameWorkspace}
                      onKeyDown={(e) => e.key === "Enter" && commitRenameWorkspace()}
                      className="min-w-0 flex-1 rounded border border-recall-border bg-transparent px-2 py-1.5 text-base text-recall-text focus:outline-none focus:border-recall-accent"
                    />
                  ) : (
                    <>
                      <button
                        onClick={() => {
                          onSelectWorkspace(ws.id);
                          setIsWorkspaceMenuOpen(false);
                        }}
                        className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-base text-recall-text hover:bg-white/5"
                      >
                        <span className="min-w-0 flex-1 truncate">{ws.name}</span>
                        {isCurrent && <CheckIcon size={13} className="flex-shrink-0 text-recall-accent" />}
                      </button>

                      {/* [더보기 ...] 버튼 */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenWsMenuId(isWsMenuOpen ? null : ws.id);
                        }}
                        aria-label="Workspace options"
                        className="hidden flex-shrink-0 px-1.5 text-recall-textMuted hover:text-recall-text group-hover:inline"
                      >
                        <MoreIcon size={15} />
                      </button>

                      {/* [더보기 ...] 드롭다운 메뉴 (이름 변경 / 팀원 관리 / 구분선 / 삭제하기) */}
                      {isWsMenuOpen && (
                        <div
                          onMouseDown={(e) => e.stopPropagation()}
                          className="absolute right-0 top-full z-40 mt-0.5 w-36 rounded-lg border border-recall-border bg-recall-bg p-1.5 shadow-xl"
                        >
                          {/* 1. 이름 변경 */}
                          <button
                            onClick={() => startRenameWorkspace(ws)}
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
                          >
                            <PencilIcon size={13} />
                            이름 변경
                          </button>

                          {/* 2. 팀원 관리 */}
                          <button
                            onClick={() => {
                              setOpenWsMenuId(null);
                              setIsWorkspaceMenuOpen(false);
                              setManagingWorkspace(ws);
                            }}
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
                          >
                            ⚙️ 팀원 관리
                          </button>

                          {/* 3. 구분선 */}
                          <div className="my-1 border-t border-recall-border" />

                          {/* 4. 삭제하기 */}
                          {onDeleteWorkspace && (
                            <button
                              onClick={() => {
                                setOpenWsMenuId(null);
                                setIsWorkspaceMenuOpen(false);
                                onDeleteWorkspace(ws.id);
                              }}
                              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-danger hover:bg-white/5"
                            >
                              <TrashIcon size={13} />
                              삭제하기
                            </button>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })}

            <div className="my-1 border-t border-recall-border" />

            <button
              onClick={() => {
                onCreateWorkspace();
                setIsWorkspaceMenuOpen(true);
              }}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-base text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            >
              <PlusIcon size={15} className="flex-shrink-0" />
              {t.sidebar_new_workspace}
            </button>
          </div>
        )}
      </div>

      {/* 2. 중앙 메인 스크롤 영역 */}
      <div className="flex-1 overflow-y-auto px-3">
        {/* 메인 그룹 */}
        <p className="mb-1.5 px-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
          {t.main_group}
        </p>

        {/* 대시보드 */}
        <button
          onClick={() => onSelectPlaceholder("dashboard")}
          className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base ${
            activePlaceholder === "dashboard"
              ? "bg-recall-accent/15 text-recall-text"
              : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
          }`}
        >
          <HomeIcon size={16} className="flex-shrink-0" />
          <span className="truncate">{t.sidebar_dashboard}</span>
        </button>

        {/* 채팅방 (채널 목록) */}
        <button
          onClick={() => setIsChannelsExpanded((v) => !v)}
          className="mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
        >
          {isChannelsExpanded ? (
            <ChevronDownIcon size={13} className="flex-shrink-0" />
          ) : (
            <ChevronRightIcon size={13} className="flex-shrink-0" />
          )}
          <ChatIcon size={16} className="flex-shrink-0" />
          <span className="truncate">{t.sidebar_chat}</span>
        </button>

        {isChannelsExpanded && (
          <div className="mb-1 flex flex-col gap-0.5 py-0.5 pl-9">
            {channels.map((channel) => {
              const isSelected = selectedChannelId === channel.id && activePlaceholder === null;
              const isEditing = editingChannelId === channel.id;
              const isMenuOpen = openMenuChannelId === channel.id;
              return (
                <div key={channel.id} className="group relative flex items-center">
                  {isEditing ? (
                    <input
                      autoFocus
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      onFocus={(e) => e.target.select()}
                      onBlur={commitRename}
                      onKeyDown={(e) => e.key === "Enter" && commitRename()}
                      className="min-w-0 flex-1 rounded-lg border border-recall-border bg-transparent px-2 py-1.5 text-base text-recall-text focus:outline-none focus:border-recall-accent"
                    />
                  ) : (
                    <>
                      <button
                        onClick={() => onSelectChannel(channel)}
                        className={`flex min-w-0 flex-1 items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-base ${
                          isSelected
                            ? "bg-recall-accent/15 text-recall-text"
                            : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
                        }`}
                      >
                        <span className="truncate">{channel.name}</span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenMenuChannelId(isMenuOpen ? null : channel.id);
                        }}
                        aria-label="Channel options"
                        className="hidden flex-shrink-0 px-1.5 text-recall-textMuted hover:text-recall-text group-hover:inline"
                      >
                        <MoreIcon size={15} />
                      </button>

                      {isMenuOpen && (
                        <div
                          onMouseDown={(e) => e.stopPropagation()}
                          className="absolute right-0 top-full z-20 mt-0.5 w-36 rounded-lg border border-recall-border bg-recall-bgSoft p-1.5 shadow-lg"
                        >
                          <button
                            onClick={() => startRename(channel)}
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
                          >
                            <PencilIcon size={13} />
                            이름 변경
                          </button>
                          <button
                            onClick={() => {
                              setOpenMenuChannelId(null);
                              onDeleteChannel(channel.id);
                            }}
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-danger hover:bg-white/5"
                          >
                            <TrashIcon size={13} />
                            삭제
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              );
            })}

            <button
              onClick={onCreateChannel}
              className="mt-0.5 flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-base text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            >
              <PlusIcon size={15} className="flex-shrink-0" />
              <span>{t.sidebar_create_channel}</span>
            </button>
          </div>
        )}

        {/* 음성 회의 */}
        <button
          onClick={() => onSelectPlaceholder("voiceMeeting")}
          className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base ${
            activePlaceholder === "voiceMeeting"
              ? "bg-recall-accent/15 text-recall-text"
              : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
          }`}
        >
          <MicIcon size={16} className="flex-shrink-0" />
          <span className="truncate">{t.sidebar_voice_meeting}</span>
          {voiceMeetingStatus && (
            <span
              className={`ml-auto h-1.5 w-1.5 flex-shrink-0 rounded-full ${
                voiceMeetingStatus === "recording" ? "bg-recall-danger" : "bg-recall-textMuted"
              }`}
              title={voiceMeetingStatus === "recording" ? t.sidebar_recording : t.sidebar_paused}
            />
          )}
        </button>

        {/* 분석 그룹 */}
        <p className="mb-1.5 mt-4 px-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
          {t.analysis_group}
        </p>
        {ANALYSIS_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              onClick={() => onSelectPlaceholder(item.key)}
              className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base ${
                activePlaceholder === item.key
                  ? "bg-recall-accent/15 text-recall-text"
                  : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
              }`}
            >
              <Icon size={16} className="flex-shrink-0" />
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* 3. 하단 프로필 영역 */}
      <ProfilePopup
        user={user}
        onOpenProfile={onOpenProfile}
        onOpenSettings={onOpenSettings}
        onLogout={onLogout}
        theme={theme}
        onToggleTheme={onToggleTheme}
        t={t}
      />

      {/* 팀원 초대 모달 */}
      {invitingWorkspace && (
        <InviteMemberModal
          workspaceId={invitingWorkspace.id}
          workspaceName={invitingWorkspace.name}
          onClose={() => setInvitingWorkspace(null)}
        />
      )}

      {/* 팀원 관리 모달 */}
      {managingWorkspace && (
        <ManageMembersModal
          workspaceId={managingWorkspace.id}
          workspaceName={managingWorkspace.name}
          currentUserId={user.id}
          onClose={() => setManagingWorkspace(null)}
          onOpenInviteModal={() => setInvitingWorkspace(managingWorkspace)}
        />
      )}
    </div>
  );
}