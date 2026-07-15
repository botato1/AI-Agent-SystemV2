import { useEffect, useRef, useState } from "react";
import { Channel, User, Workspace } from "../types";
import { Theme } from "../hooks/useTheme";
import ProfilePopup from "./ProfilePopup";
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
  lang: any; // 언어 상태 프로퍼티 추가
  t: any;    // 번역 사전 매핑 객체 추가
}

export default function Sidebar({
  workspaces,
  currentWorkspaceId,
  onSelectWorkspace,
  onCreateWorkspace,
  onRenameWorkspace,
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
  lang,
  t,
}: SidebarProps) {
  const [isChannelsExpanded, setIsChannelsExpanded] = useState(true);
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [openMenuChannelId, setOpenMenuChannelId] = useState<string | null>(null);
  const prevChannelCountRef = useRef(channels.length);

  // 워크스페이스 드롭다운 관련 상태
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const [editingWorkspaceId, setEditingWorkspaceId] = useState<string | null>(null);
  const [workspaceDraftName, setWorkspaceDraftName] = useState("");
  const workspaceMenuRef = useRef<HTMLDivElement>(null);
  const prevWorkspaceCountRef = useRef(workspaces.length);

  const currentWorkspace = workspaces.find((w) => w.id === currentWorkspaceId) ?? workspaces[0];

  const ANALYSIS_ITEMS: { key: PlaceholderKey; icon: typeof DocumentIcon; label: string }[] = [
    { key: "docAnalysis", icon: DocumentIcon, label: t.sidebar_doc_analysis },
    { key: "graph", icon: GraphIcon, label: t.sidebar_graph },
  ];

  useEffect(() => {
    if (workspaces.length > prevWorkspaceCountRef.current) {
      const newest = workspaces[workspaces.length - 1];
      setEditingWorkspaceId(newest.id);
      setWorkspaceDraftName(newest.name);
    }
    prevWorkspaceCountRef.current = workspaces.length;
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

  function startRenameWorkspace(workspace: Workspace) {
    setEditingWorkspaceId(workspace.id);
    setWorkspaceDraftName(workspace.name);
  }

  function commitRenameWorkspace() {
    if (editingWorkspaceId && workspaceDraftName.trim()) {
      onRenameWorkspace(editingWorkspaceId, workspaceDraftName.trim());
    }
    setEditingWorkspaceId(null);
  }

  useEffect(() => {
    if (channels.length > prevChannelCountRef.current) {
      const newest = channels[channels.length - 1];
      setEditingChannelId(newest.id);
      setDraftName(newest.name);
    }
    prevChannelCountRef.current = channels.length;
  }, [channels]);

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
      <div ref={workspaceMenuRef} className="relative px-3 pb-3 pt-4">
        <button
          onClick={() => setIsWorkspaceMenuOpen((v) => !v)}
          className="flex w-full items-center justify-between rounded-lg px-1 py-1 text-left hover:bg-white/5"
        >
          <span className="truncate text-sm font-semibold">{currentWorkspace?.name}</span>
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
              return (
                <div key={ws.id} className="group flex items-center">
                  {isEditing ? (
                    <input
                      autoFocus
                      value={workspaceDraftName}
                      onChange={(e) => setWorkspaceDraftName(e.target.value)}
                      onFocus={(e) => e.target.select()}
                      onBlur={commitRenameWorkspace}
                      onKeyDown={(e) => e.key === "Enter" && commitRenameWorkspace()}
                      className="min-w-0 flex-1 rounded border border-recall-border bg-transparent px-2 py-1.5 text-sm text-recall-text focus:outline-none focus:border-recall-accent"
                    />
                  ) : (
                    <>
                      <button
                        onClick={() => {
                          onSelectWorkspace(ws.id);
                          setIsWorkspaceMenuOpen(false);
                        }}
                        className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
                      >
                        <span className="min-w-0 flex-1 truncate">{ws.name}</span>
                        {isCurrent && <CheckIcon size={13} className="flex-shrink-0 text-recall-accent" />}
                      </button>
                      <button
                        onClick={() => startRenameWorkspace(ws)}
                        aria-label="Rename workspace"
                        className="hidden flex-shrink-0 px-1.5 text-recall-textMuted hover:text-recall-text group-hover:inline"
                      >
                        <PencilIcon size={13} />
                      </button>
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
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            >
              <PlusIcon size={15} className="flex-shrink-0" />
              {t.sidebar_new_workspace}
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-3">
        {/* 메인 그룹 */}
        <p className="mb-1.5 px-2 text-[11px] font-medium uppercase tracking-wide text-recall-textMuted">
          {t.main_group}
        </p>

        <button
          onClick={() => onSelectPlaceholder("dashboard")}
          className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm ${
            activePlaceholder === "dashboard"
              ? "bg-recall-accent/15 text-recall-text"
              : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
          }`}
        >
          <HomeIcon size={16} className="flex-shrink-0" />
          <span className="truncate">{t.sidebar_dashboard}</span>
        </button>

        <button
          onClick={() => setIsChannelsExpanded((v) => !v)}
          className="mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
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
                      className="min-w-0 flex-1 rounded-lg border border-recall-border bg-transparent px-2 py-1.5 text-sm text-recall-text focus:outline-none focus:border-recall-accent"
                    />
                  ) : (
                    <>
                      <button
                        onClick={() => onSelectChannel(channel)}
                        className={`flex min-w-0 flex-1 items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-sm ${
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
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-recall-text hover:bg-white/5"
                          >
                            <PencilIcon size={13} />
                            이름 변경
                          </button>
                          <button
                            onClick={() => {
                              setOpenMenuChannelId(null);
                              onDeleteChannel(channel.id);
                            }}
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-recall-danger hover:bg-white/5"
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
              className="mt-0.5 flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-sm text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            >
              <PlusIcon size={15} className="flex-shrink-0" />
              <span>{t.sidebar_create_channel}</span>
            </button>
          </div>
        )}

        <button
          onClick={() => onSelectPlaceholder("voiceMeeting")}
          className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm ${
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
        <p className="mb-1.5 mt-4 px-2 text-[11px] font-medium uppercase tracking-wide text-recall-textMuted">
          {t.analysis_group}
        </p>

        {ANALYSIS_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              onClick={() => onSelectPlaceholder(item.key)}
              className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm ${
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

      <ProfilePopup
        user={user}
        onOpenProfile={onOpenProfile}
        onOpenSettings={onOpenSettings}
        onLogout={onLogout}
        theme={theme}
        onToggleTheme={onToggleTheme}
        t={t}
      />
    </div>
  );
}