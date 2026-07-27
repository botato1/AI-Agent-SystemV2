// src/components/MainArea.tsx
import { useEffect, useRef, useState } from "react";
import { Channel, MemberActivity } from "../types"; // types.ts에서 정식 MemberActivity 타입을 가져옴 (충돌 해결!)
import {
  SendIcon,
  DocumentIcon,
  MicIcon,
  PlusIcon,
  CloseIcon,
  SparklesIcon,
  UploadIcon,
  TrashIcon,
  LinkIcon,
  WarningIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "./icons";
import { useChannelRuntime, ChatMessage, DocItem } from "../hooks/useChannelRuntime";
import { useAiChat } from "../hooks/useAiChat";
import { useRoomFiles } from "../hooks/useRoomFiles";
import { useContradictions } from "../hooks/useContradictions";
import { RoomFile } from "../services/roomFile";
import { Contradiction, ContradictionSeverity, ContradictionResolutionType } from "../services/contradiction";
import { hashAvatarColor } from "../data/avatarColors";
import Avatar from "./Avatar";

function severityBadge(severity: ContradictionSeverity) {
  const map = {
    high: { label: "높음", className: "bg-recall-danger/15 text-recall-danger" },
    medium: { label: "중간", className: "bg-amber-500/15 text-amber-400" },
    low: { label: "낮음", className: "bg-recall-textMuted/15 text-recall-textMuted" },
  } as const;
  const { label, className } = map[severity];
  return <span className={`flex-shrink-0 rounded-full px-1.5 py-0.5 text-[11px] ${className}`}>{label}</span>;
}
import DocumentPreviewModal from "./DocumentPreviewModal";
import LinkExistingDocumentModal from "./LinkExistingDocumentModal";

interface MainAreaProps {
  channel: Channel;
  workspaceId: string;
  currentUser: { id: string; name: string; avatarColor: string; avatarImageUrl: string | null };
  memberNameById: Record<string, string>;
  memberAvatarById: Record<string, string | null>;
  activeRecorderName: string | null;
  t: any; // 번역 객체 타입
}

// 메시지 발신자의 아바타 표시용 정보를 구성한다 - 내 메시지면 내 프로필,
// 다른 멤버면 멤버 목록에서 가져온 이미지 + 이름 해시 기반 색상으로 대체
function resolveSenderAvatar(
  m: ChatMessage,
  currentUser: MainAreaProps["currentUser"],
  memberAvatarById: Record<string, string | null>
) {
  if (m.isMine) {
    return { name: currentUser.name, avatarColor: currentUser.avatarColor, avatarImageUrl: currentUser.avatarImageUrl };
  }
  return {
    name: m.author,
    avatarColor: hashAvatarColor(m.senderId || m.author),
    avatarImageUrl: m.senderId ? memberAvatarById[m.senderId] ?? null : null,
  };
}

type Tab = "message" | "docs" | "aiChat";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function formatDocDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

const SHARE_MESSAGE_PATTERN = /^문서를 공유했습니다: (.+)$/;

function analysisStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "대기";
    case "processing":
      return "분석 중";
    case "completed":
      return "완료";
    case "failed":
      return "실패";
    case "excluded":
      return "제외됨";
    default:
      return status;
  }
}

// 채팅 입력창 - "+"로 문서/음성 업로드 선택
function ComposerBar({
  pendingFiles,
  onAddFiles,
  onRemovePendingFile,
  onSend,
  t,
}: {
  pendingFiles: File[];
  onAddFiles: (fileList: FileList | null) => void;
  onRemovePendingFile: (index: number) => void;
  onSend: (text: string) => void;
  t: any;
}) {
  const [input, setInput] = useState("");
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const docInputRef = useRef<HTMLInputElement>(null);
  const voiceInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isMenuOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isMenuOpen]);

  function handleSend() {
    const text = input.trim();
    if (!text && pendingFiles.length === 0) return;
    onSend(text);
    setInput("");
  }

  return (
    <div className="relative mt-3 rounded-2xl border border-recall-border bg-recall-bgSoft p-2 shadow-sm">
      <input
        ref={docInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          onAddFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <input
        ref={voiceInputRef}
        type="file"
        multiple
        accept="audio/*"
        className="hidden"
        onChange={(e) => {
          onAddFiles(e.target.files);
          e.target.value = "";
        }}
      />

      {pendingFiles.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5 px-1">
          {pendingFiles.map((file, i) => (
            <span
              key={`${file.name}-${i}`}
              className="flex items-center gap-1.5 rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1 text-sm text-recall-text"
            >
              {file.type.startsWith("audio/") ? <MicIcon size={13} /> : <DocumentIcon size={13} />}
              <span className="max-w-[140px] truncate">{file.name}</span>
              <button
                onClick={() => onRemovePendingFile(i)}
                aria-label="Remove attachment"
                className="text-recall-textMuted hover:text-recall-danger"
              >
                <CloseIcon size={13} />
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2">
        <div ref={menuRef} className="relative flex-shrink-0">
          {isMenuOpen && (
            <div className="absolute bottom-full left-0 mb-2 w-40 rounded-xl border border-recall-border bg-recall-bgSoft p-1.5 shadow-lg">
              <button
                onClick={() => {
                  setIsMenuOpen(false);
                  docInputRef.current?.click();
                }}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
              >
                <DocumentIcon size={14} />
                문서 업로드
              </button>
              <button
                onClick={() => {
                  setIsMenuOpen(false);
                  voiceInputRef.current?.click();
                }}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-text hover:bg-white/5"
              >
                <MicIcon size={14} />
                음성 업로드
              </button>
            </div>
          )}
          <button
            onClick={() => setIsMenuOpen((v) => !v)}
            aria-label="Upload"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl bg-recall-accent/10 text-recall-accent hover:bg-recall-accent/20"
          >
            <PlusIcon size={16} />
          </button>
        </div>

        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={t.chat_input_placeholder}
          rows={1}
          className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-base text-recall-text placeholder:text-recall-textMuted focus:outline-none"
        />

        <button
          onClick={handleSend}
          aria-label="Send"
          className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl transition ${
            input.trim() || pendingFiles.length > 0
              ? "bg-recall-accent text-white"
              : "bg-recall-border text-recall-textMuted"
          }`}
        >
          <SendIcon size={16} />
        </button>
      </div>
    </div>
  );
}

// 모순 감지 패널 (이 채팅방 메시지에서 감지된 모순만 필터링해서 보여줌)
function ContradictionPanel({
  contradictions,
  onResolve,
  onDismiss,
}: {
  contradictions: Contradiction[];
  onResolve: (id: string, resolutionType: ContradictionResolutionType) => void;
  onDismiss: (id: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(true);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const prevCountRef = useRef(contradictions.length);

  function toggleExpanded(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // 닫혀 있는 동안 새 모순이 감지되면 자동으로 펼침
  useEffect(() => {
    if (contradictions.length > prevCountRef.current) {
      setIsOpen((prevOpen) => (prevOpen ? prevOpen : true));
    }
    prevCountRef.current = contradictions.length;
  }, [contradictions.length]);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        title="모순 목록 펼치기"
        className="group relative flex w-8 flex-shrink-0 flex-col items-center gap-2 rounded-lg border border-recall-border bg-recall-bgSoft py-3 text-recall-textMuted transition-colors hover:border-recall-danger/40 hover:bg-white/5"
      >
        <span className="relative">
          <WarningIcon
            size={16}
            className={contradictions.length > 0 ? "text-recall-danger" : "text-recall-textMuted"}
          />
          {contradictions.length > 0 && (
            <span className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-recall-danger text-[10px] font-semibold text-white">
              {contradictions.length}
            </span>
          )}
        </span>
        <ChevronLeftIcon size={11} className="opacity-50 transition-opacity group-hover:opacity-100" />
      </button>
    );
  }

  return (
    <div className="flex w-64 flex-shrink-0 flex-col rounded-lg border border-recall-border bg-recall-bgSoft p-3">
      <div className="mb-2 flex items-center gap-1.5">
        <button
          onClick={() => setIsOpen(false)}
          title="모순 목록 접기"
          className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded hover:bg-white/5"
        >
          <ChevronRightIcon size={13} className="text-recall-textMuted" />
        </button>
        <p className="flex items-center gap-1.5 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
          <WarningIcon size={13} className="text-recall-danger" />
          모순 감지
        </p>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto">
        {contradictions.length === 0 ? (
          <p className="text-sm text-recall-textMuted">감지된 모순이 없습니다.</p>
        ) : (
          contradictions.map((c) => {
            const isExpanded = expandedIds.has(c.id);
            return (
            <div
              key={c.id}
              onClick={() => toggleExpanded(c.id)}
              className="cursor-pointer rounded-lg border border-recall-border p-2.5 hover:border-recall-accent/40"
            >
              <div className="mb-1 flex items-center justify-end">{severityBadge(c.severity)}</div>
              <p className={`mb-1 text-sm text-recall-text ${isExpanded ? "" : "line-clamp-2"}`}>
                {c.statement_text_snapshot}
              </p>
              <p className={`mb-2 text-xs text-recall-textMuted ${isExpanded ? "" : "line-clamp-1"}`}>
                기준: {c.reference_text_snapshot}
              </p>
              <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => onDismiss(c.id)}
                  className="flex-1 rounded border border-recall-border px-1.5 py-1 text-xs text-recall-textMuted hover:bg-white/5"
                >
                  무시
                </button>
                <button
                  onClick={() => onResolve(c.id, "keep_reference")}
                  className="flex-1 rounded border border-recall-border px-1.5 py-1 text-xs text-recall-text hover:bg-white/5"
                >
                  유지
                </button>
                <button
                  onClick={() => onResolve(c.id, "change_acknowledged")}
                  className="flex-1 rounded bg-recall-accent px-1.5 py-1 text-xs font-medium text-white hover:opacity-90"
                >
                  반영
                </button>
              </div>
            </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// 메시지 탭
function MessageTab({
  messages,
  onSend,
  onDeleteMessage,
  onUploadFiles,
  roomFiles,
  onOpenPreview,
  contradictions,
  onResolveContradiction,
  onDismissContradiction,
  currentUser,
  memberAvatarById,
  t,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  onDeleteMessage: (id: string) => void;
  onUploadFiles: (files: File[], kind: "file" | "voice") => void;
  roomFiles: RoomFile[];
  onOpenPreview: (documentId: string, name: string) => void;
  contradictions: Contradiction[];
  onResolveContradiction: (id: string, resolutionType: ContradictionResolutionType) => void;
  onDismissContradiction: (id: string) => void;
  currentUser: MainAreaProps["currentUser"];
  memberAvatarById: Record<string, string | null>;
  t: any;
}) {
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);
  const [contextMenu, setContextMenu] = useState<{ messageId: string; x: number; y: number } | null>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);

  const memberActivities: MemberActivity[] = t.mock_member_activities || [];

  useEffect(() => {
    if (!contextMenu) return;
    function handleClickOutside(e: MouseEvent) {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target as Node)) {
        setContextMenu(null);
      }
    }
    function closeMenu() {
      setContextMenu(null);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("scroll", closeMenu, true);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("scroll", closeMenu, true);
    };
  }, [contextMenu]);

  function addPendingFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    setPendingFiles((prev) => [...prev, ...Array.from(fileList)]);
  }

  function removePendingFile(index: number) {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index));
  }

  function handleSend(text: string) {
    if (text) onSend(text);

    if (pendingFiles.length > 0) {
      const voiceFiles = pendingFiles.filter((f) => f.type.startsWith("audio/"));
      const docFiles = pendingFiles.filter((f) => !f.type.startsWith("audio/"));
      if (docFiles.length > 0) onUploadFiles(docFiles, "file");
      if (voiceFiles.length > 0) onUploadFiles(voiceFiles, "voice");
    }

    setPendingFiles([]);
  }

 return (
    <div
      onDragEnter={(e) => {
        e.preventDefault();
        dragCounter.current += 1;
        setIsDragOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={(e) => {
        e.preventDefault();
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) setIsDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        dragCounter.current = 0;
        setIsDragOver(false);
        addPendingFiles(e.dataTransfer.files);
      }}
      className="relative flex flex-1 gap-3 overflow-hidden"
    >
      {isDragOver && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-2 rounded-lg bg-recall-bg/85 backdrop-blur-sm">
          <UploadIcon size={22} className="text-recall-accent" />
          <p className="text-lg font-medium text-recall-text">{t.drop_overlay}</p>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-3 overflow-y-auto">
          {memberActivities.map((activity: MemberActivity) =>
            activity.isAi ? (
              <div
                key={activity.name}
                className="flex items-start gap-1.5 rounded-lg border border-recall-border px-3 py-2"
              >
                <SparklesIcon size={13} className="mt-0.5 flex-shrink-0 text-recall-accent" />
                <p className="text-base text-recall-text">{activity.preview}</p>
              </div>
            ) : (
              <div key={activity.name} className="flex gap-2">
                <div className="h-7 w-7 flex-shrink-0 rounded-full bg-recall-accent/30" />
                <div className="min-w-0">
                  <p className="text-base font-medium text-recall-text">{activity.name}</p>
                  <p className="flex items-center gap-1 truncate text-base text-recall-textMuted">
                    {activity.kind === "upload" && <DocumentIcon size={13} className="flex-shrink-0" />}
                    {activity.preview}
                  </p>
                </div>
              </div>
            )
          )}

          {messages.map((m) => (
            <div
              key={m.id}
              className="flex items-start gap-2"
              onContextMenu={(e) => {
                if (!m.isMine) return;
                e.preventDefault();
                setContextMenu({ messageId: m.id, x: e.clientX, y: e.clientY });
              }}
            >
              <Avatar user={resolveSenderAvatar(m, currentUser, memberAvatarById)} size={28} />
              <div className="min-w-0 flex-1">
                <p className="text-base font-medium text-recall-text">{m.author}</p>
                {(() => {
                  const shareMatch = m.text.match(SHARE_MESSAGE_PATTERN);
                  const sharedFile = shareMatch
                    ? roomFiles.find((f) => f.original_filename === shareMatch[1])
                    : null;

                  if (shareMatch && sharedFile) {
                    return (
                      <button
                        onClick={() => onOpenPreview(sharedFile.id, sharedFile.original_filename)}
                        className="mt-0.5 flex items-center gap-1.5 rounded-lg border border-recall-border bg-recall-bgMain px-2.5 py-1.5 text-sm text-recall-accent hover:border-recall-accent/50"
                      >
                        <DocumentIcon size={13} className="flex-shrink-0" />
                        <span className="truncate">{sharedFile.original_filename}</span>
                      </button>
                    );
                  }

                  return <p className="text-base text-recall-textMuted">{m.text}</p>;
                })()}
              </div>
            </div>
          ))}
        </div>

        {contextMenu && (
          <div
            ref={contextMenuRef}
            style={{ position: "fixed", top: contextMenu.y, left: contextMenu.x }}
            className="z-50 w-32 rounded-lg border border-recall-border bg-recall-bgSoft p-1.5 shadow-lg"
          >
            <button
              onClick={() => {
                onDeleteMessage(contextMenu.messageId);
                setContextMenu(null);
              }}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-recall-danger hover:bg-white/5"
            >
              <TrashIcon size={13} />
              삭제하기
            </button>
          </div>
        )}

        <ComposerBar
          pendingFiles={pendingFiles}
          onAddFiles={addPendingFiles}
          onRemovePendingFile={removePendingFile}
          onSend={handleSend}
          t={t}
        />
      </div>

      <ContradictionPanel
        contradictions={contradictions}
        onResolve={onResolveContradiction}
        onDismiss={onDismissContradiction}
      />
    </div>
  );
}

// 문서보관함 탭
function DocsTab({
  docs,
  onUploadFiles,
  onRemoveDoc,
  onLinkExisting,
  onOpenPreview,
  t,
}: {
  docs: DocItem[];
  onUploadFiles: (fileList: FileList | null, kind: "file" | "voice") => void;
  onRemoveDoc: (id: string) => void;
  onLinkExisting: () => void;
  onOpenPreview: (documentId: string, name: string) => void;
  t: any;
}) {
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragEnter={(e) => {
        e.preventDefault();
        dragCounter.current += 1;
        setIsDragOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={(e) => {
        e.preventDefault();
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) setIsDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        dragCounter.current = 0;
        setIsDragOver(false);
        onUploadFiles(e.dataTransfer.files, "file");
      }}
      className="relative flex flex-1 flex-col overflow-y-auto"
    >
      {isDragOver && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-2 rounded-lg bg-recall-bg/85 backdrop-blur-sm">
          <UploadIcon size={22} className="text-recall-accent" />
          <p className="text-lg font-medium text-recall-text">{t.drop_overlay}</p>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          onUploadFiles(e.target.files, "file");
          e.target.value = "";
        }}
      />

      <div className="mb-3 flex gap-2">
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-recall-border px-3 py-6 text-center hover:bg-white/5"
        >
          <p className="text-base text-recall-text">{t.docs_tab_msg}</p>
          <p className="mt-1 text-sm text-recall-textMuted">{t.docs_tab_sub}</p>
        </button>
        <button
          onClick={onLinkExisting}
          className="flex flex-shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-recall-border px-4 py-6 text-center hover:bg-white/5"
        >
          <LinkIcon size={16} className="text-recall-textMuted" />
          <p className="text-sm text-recall-textMuted">기존 문서 연결</p>
        </button>
      </div>

      <div className="space-y-2">
        {docs.map((doc) => (
          <div
            key={doc.id}
            onClick={() => doc.kind === "file" && onOpenPreview(doc.id, doc.name)}
            className={`group flex items-center justify-between rounded-lg border border-recall-border px-3 py-2 text-base ${
              doc.kind === "file" ? "cursor-pointer hover:border-recall-accent/50" : ""
            }`}
          >
            <span className="flex min-w-0 items-center gap-2 text-recall-text">
              <span className="flex-shrink-0 text-recall-textMuted">
                {doc.kind === "voice" ? <MicIcon size={15} /> : <DocumentIcon size={15} />}
              </span>
              <span className="truncate">{doc.name}</span>
            </span>
            <span className="flex flex-shrink-0 items-center gap-2 text-sm text-recall-textMuted">
              {doc.statusLabel ?? formatFileSize(doc.size)} · {doc.date}
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  onRemoveDoc(doc.id);
                }}
                className="hidden hover:text-recall-danger group-hover:inline"
              >
                <CloseIcon size={13} />
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// AI Chat 탭
function ThinkingDots() {
  return (
    <span className="flex items-center gap-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted" />
    </span>
  );
}

function AiChatTab({ workspaceId, roomId, t }: { workspaceId: string; roomId: string; t: any }) {
  const { messages, isLoading, isSending, sendMessage } = useAiChat(workspaceId, roomId);
  const [input, setInput] = useState("");

  function handleSend() {
    if (!input.trim() || isSending) return;
    sendMessage(input);
    setInput("");
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-1 py-2">
        {isLoading ? (
          <p className="text-base text-recall-textMuted">불러오는 중...</p>
        ) : messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-recall-accent/15">
              <SparklesIcon size={18} className="text-recall-accent" />
            </div>
            <p className="text-base text-recall-textMuted">{t.ai_chat_welcome}</p>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex items-end gap-2 ${m.role === "assistant" ? "" : "flex-row-reverse"}`}
            >
              <div className={`flex max-w-[75%] flex-col gap-1 ${m.role === "assistant" ? "items-start" : "items-end"}`}>
                <div
                  className={`whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-base leading-relaxed shadow-sm ${
                    m.role === "assistant"
                      ? "rounded-bl-md bg-recall-bgSoft text-recall-text"
                      : "rounded-br-md bg-recall-accent text-white"
                  } ${m.isPending || m.errorText ? "opacity-60" : ""}`}
                >
                  {m.content}
                </div>
                {m.errorText && (
                  <p className="flex items-center gap-1 text-xs text-recall-danger">
                    <WarningIcon size={12} /> {m.errorText}
                  </p>
                )}
              </div>
            </div>
          ))
        )}
        {isSending && (
          <div className="flex items-end gap-2">
            <div className="rounded-2xl rounded-bl-md bg-recall-bgSoft px-3.5 py-2.5 shadow-sm">
              <ThinkingDots />
            </div>
          </div>
        )}
      </div>
      <div className="relative mt-3 flex items-center gap-2 rounded-2xl border border-recall-border bg-recall-bgSoft p-2 shadow-sm">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder={t.ai_input_placeholder}
          className="flex-1 bg-transparent px-2 py-1.5 text-base text-recall-text placeholder:text-recall-textMuted focus:outline-none"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || isSending}
          aria-label="Send"
          className="flex flex-shrink-0 items-center justify-center rounded-full bg-recall-accent p-2 text-white transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          <SendIcon size={14} />
        </button>
      </div>
    </div>
  );
}

export default function MainArea({
  channel,
  workspaceId,
  currentUser,
  memberNameById,
  memberAvatarById,
  activeRecorderName,
  t,
}: MainAreaProps) {
  const [activeTab, setActiveTab] = useState<Tab>("message");

  const { chatMessages, docs, sendChatMessage, deleteMessage, addDocFiles, removeDoc } = useChannelRuntime(
    workspaceId,
    channel.id,
    currentUser,
    memberNameById
  );

  const roomFiles = useRoomFiles(workspaceId, channel.id);

  // 이 채팅방 메시지에서 감지된 모순만 필터링 (회의 발언 쪽 모순은 회의 화면에서 따로 보여줌)
  const { contradictions: workspaceContradictions, resolve: resolveContradiction, dismiss: dismissContradiction } =
    useContradictions(workspaceId);
  const roomContradictions = workspaceContradictions.filter(
    (c) => c.source_type === "room_message" && c.room_message_id && chatMessages.some((m) => m.id === c.room_message_id)
  );

  const mergedDocs: DocItem[] = [
    ...roomFiles.files.map((f) => ({
      id: f.id,
      name: f.original_filename,
      size: 0,
      statusLabel: analysisStatusLabel(f.analysis_status),
      date: formatDocDate(f.created_at),
      kind: "file" as const,
    })),
    ...docs.filter((d) => d.kind === "voice"),
  ];

  // 채팅창 "+"로 문서를 올리면 실제로 업로드하고(room_id로 자동 연결), 성공하면 공유 메시지를 남김
  async function handleUploadFromChat(files: File[], kind: "file" | "voice") {
    if (kind === "voice") {
      addDocFiles(files, "voice", true);
      return;
    }
    for (const file of files) {
      const ok = await roomFiles.uploadFile(file);
      if (ok) sendChatMessage(`문서를 공유했습니다: ${file.name}`);
    }
  }

  // 문서보관함 탭의 업로드는 항상 문서(document) 종류
  async function handleUploadFromDocsTab(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    for (const file of Array.from(fileList)) {
      await roomFiles.uploadFile(file);
    }
  }

  function handleRemoveDoc(id: string) {
    if (roomFiles.files.some((f) => f.id === id)) {
      roomFiles.removeFile(id);
    } else {
      removeDoc(id);
    }
  }

  const [showLinkModal, setShowLinkModal] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<{ id: string; name: string } | null>(null);

  const tabs: { id: Tab; label: string }[] = [
    { id: "message", label: t.chat_tab_message },
    { id: "docs", label: t.chat_tab_docs },
    { id: "aiChat", label: t.chat_tab_ai },
  ];

  const participants = Object.entries(memberNameById).map(([id, name]) => ({ id, name }));

  return (
    <div className="flex h-full flex-1 flex-col bg-recall-bgMain p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="truncate text-sm font-medium text-recall-text">{channel.name}</p>
        <div className="flex items-center gap-1">
          <div className="flex -space-x-1.5">
            {participants.map(({ id, name }) => {
              const isRecording = name === activeRecorderName;
              return (
                <div key={id} title={isRecording ? `${name} · ${t.sidebar_recording}` : name} className="relative">
                  <div
                    className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border-2 text-[11px] font-semibold text-white ${
                      isRecording ? "border-recall-danger" : "border-recall-bgMain"
                    }`}
                    style={{ backgroundColor: hashAvatarColor(id) }}
                  >
                    {name.slice(0, 1).toUpperCase()}
                  </div>
                  {isRecording && (
                    <span className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-recall-danger text-white">
                      <MicIcon size={8} />
                    </span>
                  )}
                </div>
              );
            })}
          </div>
          <span className="ml-1 text-sm text-recall-textMuted">{participants.length}</span>
        </div>
      </div>

      <div className="mb-2 flex gap-0.5 border-b border-recall-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-2 py-1 text-sm ${
              activeTab === tab.id
                ? "border-b-2 border-recall-accent text-recall-text"
                : "text-recall-textMuted hover:text-recall-text"
              }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "message" && (
        <MessageTab
          messages={chatMessages}
          onSend={sendChatMessage}
          onDeleteMessage={deleteMessage}
          onUploadFiles={handleUploadFromChat}
          roomFiles={roomFiles.files}
          onOpenPreview={(id, name) => setPreviewDoc({ id, name })}
          contradictions={roomContradictions}
          onResolveContradiction={resolveContradiction}
          onDismissContradiction={dismissContradiction}
          currentUser={currentUser}
          memberAvatarById={memberAvatarById}
          t={t}
        />
      )}
      {activeTab === "docs" && (
        <DocsTab
          docs={mergedDocs}
          onUploadFiles={(fileList) => handleUploadFromDocsTab(fileList)}
          onRemoveDoc={handleRemoveDoc}
          onLinkExisting={() => setShowLinkModal(true)}
          onOpenPreview={(id, name) => setPreviewDoc({ id, name })}
          t={t}
        />
      )}
      {activeTab === "aiChat" && <AiChatTab workspaceId={workspaceId} roomId={channel.id} t={t} />}

      {showLinkModal && (
        <LinkExistingDocumentModal
          workspaceId={workspaceId}
          excludeIds={roomFiles.files.map((f) => f.id)}
          onClose={() => setShowLinkModal(false)}
          onLink={roomFiles.linkExistingFile}
        />
      )}

      {previewDoc && (
        <DocumentPreviewModal
          workspaceId={workspaceId}
          documentId={previewDoc.id}
          documentName={previewDoc.name}
          onClose={() => setPreviewDoc(null)}
        />
      )}
    </div>
  );
}