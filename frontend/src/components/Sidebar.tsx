// src/components/Sidebar.tsx
import { useEffect, useRef, useState } from "react";
import { Channel, User, Workspace } from "../types";
import { Theme } from "../hooks/useTheme";
import { Category } from "../services/category";
import { getCategoryColor } from "../utils/categoryColor";
import { showConfirm } from "../lib/confirm";
import ProfilePopup from "./ProfilePopup";
import NotificationBell from "./NotificationBell";
import InviteMemberModal from "./InviteMemberModal";
import ManageMembersModal from "./ManageMembersModal";
import {
  HomeIcon,
  GridIcon,
  ChatIcon,
  InsightIcon,
  DocumentIcon,
  MicIcon,
  GraphIcon,
  PlusIcon,
  MoreIcon,
  PencilIcon,
  TrashIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ChevronRightIcon,
  CheckIcon,
  PinIcon,
  CloseIcon,
} from "./icons";

export type PlaceholderKey = "home" | "dashboard" | "docAnalysis" | "voiceMeeting" | "graph" | "aiChat";

// 자주 쓰는 카테고리를 사용자가 직접 고정해서 맨 위에 두는 기능 - 워크스페이스별로 브라우저에
// 저장해서 새로고침해도 유지된다. "최근에 누른 게 자동으로 맨 위로" 가는 방식은 번갈아 쓰는
// 카테고리들의 위치가 클릭할 때마다 계속 바뀌어서 위치를 외우기 어렵다는 문제가 있어, 고정한
// 것만 위치가 바뀌고 나머지는 원래 순서를 유지하는 수동 고정 방식으로 바꿨다.
const CATEGORY_PIN_STORAGE_PREFIX = "recall:pinned_categories:";

function loadPinnedCategories(workspaceId: string): string[] {
  try {
    const raw = localStorage.getItem(CATEGORY_PIN_STORAGE_PREFIX + workspaceId);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function savePinnedCategories(workspaceId: string, ids: string[]) {
  try {
    localStorage.setItem(CATEGORY_PIN_STORAGE_PREFIX + workspaceId, JSON.stringify(ids));
  } catch {
    // 저장 공간이 꽉 찼거나 접근 불가해도 고정 기능 자체는 세션 중엔 계속 동작해야 하므로 무시
  }
}

interface SidebarProps {
  workspaces: Workspace[];
  currentWorkspaceId: string;
  onSelectWorkspace: (id: string) => void;
  onCreateWorkspace: () => void;
  onRenameWorkspace: (id: string, name: string) => void;
  onDeleteWorkspace?: (id: string) => void;
  channels: Channel[];
  selectedChannelId: string | null;
  categories: Category[];
  selectedCategoryId: string | null;
  onSelectCategory: (id: string | null) => void;
  onCreateCategory: (name: string) => void;
  onRenameCategory: (id: string, name: string) => void;
  onDeleteCategory: (id: string) => void;
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
  // 모바일(md 미만)에서는 사이드바가 기본 숨김 + 오버레이로 여닫히고, 데스크톱에서는 이
  // 값과 무관하게 항상 보인다 (아래 className에서 md: 접두사로 처리).
  isMobileOpen: boolean;
  onCloseMobile: () => void;
}

export default function Sidebar({
  isMobileOpen,
  onCloseMobile,
  workspaces,
  currentWorkspaceId,
  onSelectWorkspace,
  onCreateWorkspace,
  onRenameWorkspace,
  onDeleteWorkspace,
  channels,
  selectedChannelId,
  categories,
  selectedCategoryId,
  onSelectCategory,
  onCreateCategory,
  onRenameCategory,
  onDeleteCategory,
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
  // 카테고리가 계속 늘어나면 사이드바가 한없이 길어지니, 기본으로는 일부만 보여주고 접어둔다.
  const [isCategoryListExpanded, setIsCategoryListExpanded] = useState(false);
  const [isAddingCategory, setIsAddingCategory] = useState(false);
  const [newCategoryDraftName, setNewCategoryDraftName] = useState("");
  const addCategoryRef = useRef<HTMLDivElement>(null);

  const [pinnedCategoryIds, setPinnedCategoryIds] = useState<string[]>(() =>
    loadPinnedCategories(currentWorkspaceId)
  );
  useEffect(() => {
    setPinnedCategoryIds(loadPinnedCategories(currentWorkspaceId));
  }, [currentWorkspaceId]);

  function handleSelectCategory(id: string | null) {
    // 카테고리를 고르면, "더보기"를 펼쳐서 찾아 눌렀더라도 매번 수동으로 접을 필요 없이
    // 바로 접어준다.
    if (id) setIsCategoryListExpanded(false);
    onSelectCategory(id);
  }

  function togglePinCategory(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    setPinnedCategoryIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      savePinnedCategories(currentWorkspaceId, next);
      return next;
    });
  }

  // 카테고리 이름변경/삭제는 우클릭 메뉴로 처리한다 - 호버 아이콘을 더 늘리면(핀에 이어
  // 연필/휴지통까지) 좁은 사이드바 한 줄에 아이콘이 너무 빽빽해지고, 이 앱에 이미 우클릭
  // 컨텍스트 메뉴 패턴이 있어서(채팅 메시지 삭제, MainArea.tsx) 그걸 재사용한다.
  const [editingCategoryId, setEditingCategoryId] = useState<string | null>(null);
  const [categoryDraftName, setCategoryDraftName] = useState("");
  const [categoryContextMenu, setCategoryContextMenu] = useState<{ id: string; x: number; y: number } | null>(
    null
  );
  const categoryContextMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!categoryContextMenu) return;
    function handleClickOutside(e: MouseEvent) {
      if (categoryContextMenuRef.current && !categoryContextMenuRef.current.contains(e.target as Node)) {
        setCategoryContextMenu(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [categoryContextMenu]);

  function startRenameCategory(cat: Category) {
    setEditingCategoryId(cat.id);
    setCategoryDraftName(cat.name);
    setCategoryContextMenu(null);
  }

  function commitRenameCategory() {
    if (editingCategoryId && categoryDraftName.trim()) {
      onRenameCategory(editingCategoryId, categoryDraftName.trim());
    }
    setEditingCategoryId(null);
  }

  async function handleDeleteCategoryFromMenu(cat: Category) {
    setCategoryContextMenu(null);
    const ok = await showConfirm(
      t.settings_category_delete_confirm(cat.name),
      t.settings_account_delete_confirm_btn,
      t.task_cancel
    );
    if (ok) onDeleteCategory(cat.id);
  }

  // 고정한 카테고리만 맨 앞으로 오도록 재정렬한다. 고정 안 한 것끼리는 원래 순서를 그대로
  // 유지한다 (Array.sort는 동률일 때 상대 순서를 보존하므로 안정적으로 유지됨) - 그래야
  // 번갈아 쓰는 카테고리들 위치가 클릭할 때마다 바뀌지 않는다.
  const orderedCategories = [...categories].sort((a, b) => {
    const aPinned = pinnedCategoryIds.includes(a.id);
    const bPinned = pinnedCategoryIds.includes(b.id);
    if (aPinned === bPinned) return 0;
    return aPinned ? -1 : 1;
  });

  useEffect(() => {
    if (!isAddingCategory) return;
    function handleClickOutside(e: MouseEvent) {
      if (addCategoryRef.current && !addCategoryRef.current.contains(e.target as Node)) {
        setIsAddingCategory(false);
        setNewCategoryDraftName("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isAddingCategory]);

  function handleConfirmAddCategory() {
    const name = newCategoryDraftName.trim();
    if (!name) return;
    onCreateCategory(name);
    setIsAddingCategory(false);
    setNewCategoryDraftName("");
  }

  const [editingChannelId, setEditingChannelId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [openMenuChannelId, setOpenMenuChannelId] = useState<string | null>(null);
  const prevChannelIdsRef = useRef<Set<string>>(new Set(channels.map((c) => c.id)));
  const prevWorkspaceIdForChannelsRef = useRef(currentWorkspaceId);

  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const [editingWorkspaceId, setEditingWorkspaceId] = useState<string | null>(null);
  const [workspaceDraftName, setWorkspaceDraftName] = useState("");
  const [openWsMenuId, setOpenWsMenuId] = useState<string | null>(null);

  const [invitingWorkspace, setInvitingWorkspace] = useState<Workspace | null>(null);
  const [managingWorkspace, setManagingWorkspace] = useState<Workspace | null>(null);

  const workspaceMenuRef = useRef<HTMLDivElement>(null);
  const prevWorkspaceIdsRef = useRef<Set<string>>(new Set(workspaces.map((w) => w.id)));

  const currentWorkspace = workspaces.find((w) => w.id === currentWorkspaceId) ?? workspaces[0];

  useEffect(() => {
    const prevIds = prevWorkspaceIdsRef.current;
    const newOnes = workspaces.filter((w) => !prevIds.has(w.id));

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
    <div
      // CSS에서 transform 값은 translateX(0)처럼 실질적으로 아무 효과가 없어도 그 요소를
      // 새 쌓임 맥락(stacking context)으로 만들어버린다. md 이상에서도 md:translate-x-0를
      // 항상 걸어두면 데스크톱에서도 사이드바가 쌓임 맥락이 돼서, 그 안의 알림 드롭다운
      // (z-50)이 "사이드바 안에서만" 맨 위일 뿐 사이드바 바깥 본문과 비교해선 더 이상
      // 제대로 위에 뜨지 못해 본문과 뒤섞여 보이는 버그가 있었다. md 미만(모바일)에서만
      // translate 클래스가 적용되게 해서, 데스크톱에선 transform 자체가 아예 안 붙어
      // 쌓임 맥락이 생기지 않게 한다 (= 예전처럼 전역 z-index 비교로 정상 작동).
      className={`fixed inset-y-0 left-0 z-40 flex h-full w-64 flex-shrink-0 flex-col bg-recall-bg text-recall-text select-none transition-transform duration-200 ease-out md:static md:z-auto ${
        isMobileOpen ? "max-md:translate-x-0" : "max-md:-translate-x-full"
      }`}
    >
      {/* 1. 상단 워크스페이스 선택 영역 */}
      <div ref={workspaceMenuRef} className="relative flex items-center gap-1 px-3 pb-3 pt-4">
        <button
          onClick={() => setIsWorkspaceMenuOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-white/5 transition"
        >
          <span className="truncate text-base font-semibold">{currentWorkspace?.name}</span>
          <ChevronDownIcon
            size={14}
            className={`flex-shrink-0 text-recall-textMuted transition-transform ${
              isWorkspaceMenuOpen ? "rotate-180" : ""
            }`}
          />
        </button>
        <button
          onClick={onCloseMobile}
          title={t.sidebar_collapse_sidebar}
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-recall-textMuted hover:bg-white/5 md:hidden"
        >
          <CloseIcon size={16} />
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

                      {isWsMenuOpen && (
                        <div
                          onMouseDown={(e) => e.stopPropagation()}
                          className="absolute right-0 top-full z-40 mt-0.5 w-36 rounded-lg border border-recall-border bg-recall-bg p-1.5 shadow-xl"
                        >
                          <button
                            onClick={() => startRenameWorkspace(ws)}
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
                          >
                            <PencilIcon size={13} />
                            {t.chat_option_rename}
                          </button>

                          <button
                            onClick={() => {
                              setOpenWsMenuId(null);
                              setIsWorkspaceMenuOpen(false);
                              setManagingWorkspace(ws);
                            }}
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
                          >
                            {t.sidebar_manage_members_menu}
                          </button>

                          <div className="my-1 border-t border-recall-border" />

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
                              {t.sidebar_delete_workspace}
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

      {/* 2. 중앙 스크롤 메인 메뉴 영역 */}
      <div className="flex-1 overflow-y-auto px-3 space-y-4 custom-scrollbar">
        {/* 카테고리 선택기 - 워크스페이스 전환기처럼 여기서 고른 카테고리가 회의/문서 등
            여러 페이지의 필터로 전역 적용된다. 홈/그래프 뷰는 이 필터를 적용받지 않는다. */}
        <div ref={addCategoryRef}>
          <div className="mb-1.5 flex items-center justify-between px-2">
            <p className="text-xs font-medium uppercase tracking-wide text-recall-textMuted">
              {t.sidebar_category_group || "CATEGORIES"}
            </p>
            {!isAddingCategory && (
              <button
                onClick={() => setIsAddingCategory(true)}
                title={t.meeting_category_add_btn}
                className="text-recall-textMuted hover:text-recall-accent"
              >
                <PlusIcon size={13} />
              </button>
            )}
          </div>
          {isAddingCategory && (
            <div className="mb-1.5 flex gap-1.5">
              <input
                autoFocus
                value={newCategoryDraftName}
                onChange={(e) => setNewCategoryDraftName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleConfirmAddCategory();
                  if (e.key === "Escape") setIsAddingCategory(false);
                }}
                placeholder={t.meeting_category_create_placeholder}
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-2.5 py-1.5 text-sm text-recall-text outline-none focus:border-recall-accent"
              />
              <button
                onClick={handleConfirmAddCategory}
                disabled={!newCategoryDraftName.trim()}
                className="flex-shrink-0 rounded-lg bg-recall-accent px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
              >
                {t.meeting_category_create_confirm}
              </button>
            </div>
          )}
          <button
            onClick={() => handleSelectCategory(null)}
            className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base transition ${
              selectedCategoryId === null
                ? "bg-recall-accent/15 text-recall-text font-medium"
                : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            }`}
          >
            <GridIcon size={16} className="flex-shrink-0" />
            <span className="truncate">{t.sidebar_category_all || "All"}</span>
          </button>
          {(() => {
            const CAP = 3;
            const selectedIndex = orderedCategories.findIndex((c) => c.id === selectedCategoryId);
            // 접힌 상태에서도 지금 선택 중인 카테고리는 목록에서 안 사라지게 포함시킨다.
            const needsSelectedPin = !isCategoryListExpanded && selectedIndex >= CAP;
            const visibleCategories = isCategoryListExpanded
              ? orderedCategories
              : needsSelectedPin
              ? [orderedCategories[selectedIndex], ...orderedCategories.slice(0, CAP - 1)]
              : orderedCategories.slice(0, CAP);
            const hiddenCount = orderedCategories.length - visibleCategories.length;

            return (
              <>
                {visibleCategories.map((cat) => {
                  const index = categories.indexOf(cat);
                  const isPinned = pinnedCategoryIds.includes(cat.id);
                  const isEditing = editingCategoryId === cat.id;
                  return (
                    <div
                      key={cat.id}
                      onContextMenu={(e) => {
                        if (cat.is_default) return;
                        e.preventDefault();
                        setCategoryContextMenu({ id: cat.id, x: e.clientX, y: e.clientY });
                      }}
                      className={`group mb-0.5 flex w-full items-center rounded-lg transition ${
                        selectedCategoryId === cat.id
                          ? "bg-recall-accent/15 text-recall-text font-medium"
                          : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
                      }`}
                    >
                      {isEditing ? (
                        <input
                          autoFocus
                          value={categoryDraftName}
                          onChange={(e) => setCategoryDraftName(e.target.value)}
                          onFocus={(e) => e.target.select()}
                          onBlur={commitRenameCategory}
                          onKeyDown={(e) => e.key === "Enter" && commitRenameCategory()}
                          className="min-w-0 flex-1 rounded-lg border border-recall-border bg-transparent px-2.5 py-1.5 text-base text-recall-text focus:outline-none focus:border-recall-accent"
                        />
                      ) : (
                        <>
                          <button
                            onClick={() => handleSelectCategory(cat.id)}
                            className="flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-2 text-left text-base"
                          >
                            <span
                              className="h-2 w-2 flex-shrink-0 rounded-full"
                              style={{ backgroundColor: getCategoryColor(index) }}
                            />
                            <span className="truncate">
                              {cat.is_default ? t.meeting_category_default_label : cat.name}
                            </span>
                          </button>
                          <button
                            onClick={(e) => togglePinCategory(cat.id, e)}
                            title={isPinned ? "고정 해제" : "맨 위에 고정"}
                            className={`mr-1.5 flex-shrink-0 rounded p-1 transition ${
                              isPinned
                                ? "text-recall-accent"
                                : "text-recall-textMuted opacity-0 hover:text-recall-text group-hover:opacity-100"
                            }`}
                          >
                            <PinIcon size={12} className={isPinned ? "fill-current" : ""} />
                          </button>
                        </>
                      )}
                    </div>
                  );
                })}
                {categoryContextMenu &&
                  (() => {
                    const menuCategory = categories.find((c) => c.id === categoryContextMenu.id);
                    if (!menuCategory) return null;
                    return (
                      <div
                        ref={categoryContextMenuRef}
                        style={{ position: "fixed", top: categoryContextMenu.y, left: categoryContextMenu.x }}
                        className="z-50 w-32 rounded-lg border border-recall-border bg-recall-bgSoft p-1.5 shadow-lg"
                      >
                        <button
                          onClick={() => startRenameCategory(menuCategory)}
                          className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
                        >
                          <PencilIcon size={13} />
                          {t.chat_option_rename}
                        </button>
                        <button
                          onClick={() => handleDeleteCategoryFromMenu(menuCategory)}
                          className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-danger hover:bg-white/5"
                        >
                          <TrashIcon size={13} />
                          {t.chat_option_delete}
                        </button>
                      </div>
                    );
                  })()}
                {categories.length > CAP && (
                  <button
                    onClick={() => setIsCategoryListExpanded((v) => !v)}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-sm text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
                  >
                    {isCategoryListExpanded ? (
                      <>
                        <ChevronUpIcon size={13} className="flex-shrink-0" />
                        {t.sidebar_category_collapse || "Show less"}
                      </>
                    ) : (
                      <>
                        <ChevronDownIcon size={13} className="flex-shrink-0" />
                        {(t.sidebar_category_show_more || ((n: number) => `${n} more`))(hiddenCount)}
                      </>
                    )}
                  </button>
                )}
              </>
            );
          })()}
        </div>

        {/* 그룹 1: 메인 (MAIN) */}
        <div>
          <p className="mb-1.5 px-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
            {t.main_group || "MAIN"}
          </p>

          {/* 홈 */}
          <button
            onClick={() => onSelectPlaceholder("home")}
            className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base transition ${
              activePlaceholder === "home"
                ? "bg-recall-accent/15 text-recall-text font-medium"
                : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            }`}
          >
            <HomeIcon size={16} className="flex-shrink-0" />
            <span className="truncate">{t.sidebar_home}</span>
          </button>

          {/* 대시보드 */}
          <button
            onClick={() => onSelectPlaceholder("dashboard")}
            className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base transition ${
              activePlaceholder === "dashboard"
                ? "bg-recall-accent/15 text-recall-text font-medium"
                : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            }`}
          >
            <GridIcon size={16} className="flex-shrink-0" />
            <span className="truncate">{t.sidebar_dashboard}</span>
          </button>
        </div>
        {/* 그룹 2: 워크스페이스 핵심 기능 (WORKSPACE) */}
        <div>

          {/* 🌟 최상단으로 끌어올린 메인 액션: 음성 회의 */}
          <button
            onClick={() => onSelectPlaceholder("voiceMeeting")}
            className={`mb-1 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base transition ${
              activePlaceholder === "voiceMeeting"
                ? "bg-recall-accent/15 text-recall-text font-medium"
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

          {/* 채팅방 (채널 목록) */}
          <button
            onClick={() => setIsChannelsExpanded((v) => !v)}
            className="mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base text-recall-textMuted hover:bg-white/5 hover:text-recall-text transition"
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
            <div className="mb-1 flex flex-col gap-0.5 py-0.5 pl-8">
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
                          className={`flex min-w-0 flex-1 items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-base transition ${
                            isSelected
                              ? "bg-recall-accent/15 text-recall-text font-medium"
                              : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
                          }`}
                        >
                          {(() => {
                            const categoryIndex = categories.findIndex((c) => c.id === channel.category_id);
                            const cat = categoryIndex >= 0 ? categories[categoryIndex] : null;
                            if (!cat || cat.is_default) return null;
                            return (
                              <span
                                title={cat.name}
                                className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
                                style={{ backgroundColor: getCategoryColor(categoryIndex) }}
                              />
                            );
                          })()}
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
                              {t.chat_option_rename}
                            </button>
                            <button
                              onClick={() => {
                                setOpenMenuChannelId(null);
                                onDeleteChannel(channel.id);
                              }}
                              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-danger hover:bg-white/5"
                            >
                              <TrashIcon size={13} />
                              {t.chat_option_delete}
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
                className="mt-0.5 flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-base text-recall-textMuted hover:bg-white/5 hover:text-recall-text transition"
              >
                <PlusIcon size={15} className="flex-shrink-0" />
                <span>{t.sidebar_create_channel}</span>
              </button>
            </div>
          )}
        </div>

        {/* 그룹 3: 지식 및 분석 (KNOWLEDGE & ANALYTICS) */}
        <div>
          <p className="mb-1.5 px-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
            {t.analysis_group || "KNOWLEDGE & ANALYTICS"}
          </p>

          {/* 회의 자료 (문서 분석) */}
          <button
            onClick={() => onSelectPlaceholder("docAnalysis")}
            className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base transition ${
              activePlaceholder === "docAnalysis"
                ? "bg-recall-accent/15 text-recall-text font-medium"
                : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            }`}
          >
            <DocumentIcon size={16} className="flex-shrink-0" />
            <span className="truncate">{t.sidebar_doc_analysis}</span>
          </button>

          {/* AI 인사이트 */}
          <button
            onClick={() => onSelectPlaceholder("aiChat")}
            className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base transition ${
              activePlaceholder === "aiChat"
                ? "bg-recall-accent/15 text-recall-text font-medium"
                : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            }`}
          >
            <InsightIcon size={16} className="flex-shrink-0" />
            <span className="truncate font-medium">{t.ai_chat_page_title}</span>
          </button>

          {/* 그래프 뷰 */}
          <button
            onClick={() => onSelectPlaceholder("graph")}
            className={`mb-0.5 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-base transition ${
              activePlaceholder === "graph"
                ? "bg-recall-accent/15 text-recall-text font-medium"
                : "text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
            }`}
          >
            <GraphIcon size={16} className="flex-shrink-0" />
            <span className="truncate">{t.sidebar_graph}</span>
          </button>
        </div>
      </div>

      {/* 3. 하단 사용자 프로필 및 알림 영역 - 디스코드/슬랙처럼 프로필과 보조 아이콘을 한 줄에
          나란히 두되, 서로 완전히 독립된 버튼으로 둔다 (하나가 다른 하나를 덮거나 클릭
          영역이 겹치지 않음) */}
      <div className="flex items-center gap-1.5 border-t border-recall-border px-2 pb-2 pt-2">
        <ProfilePopup
          user={user}
          onOpenProfile={onOpenProfile}
          onOpenSettings={onOpenSettings}
          onLogout={onLogout}
          theme={theme}
          onToggleTheme={onToggleTheme}
          t={t}
        />
        <NotificationBell
          workspaceId={currentWorkspaceId}
          channels={channels}
          onSelectChannel={onSelectChannel}
          onSelectPlaceholder={onSelectPlaceholder}
        />
      </div>

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
          t={t}
        />
      )}
    </div>
  );
}