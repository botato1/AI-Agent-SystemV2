// src/components/MainArea.tsx
import { useEffect, useRef, useState } from "react";
import { Channel, MemberActivity } from "../types";
import {
  SendIcon,
  DocumentIcon,
  MicIcon,
  PlusIcon,
  CloseIcon,
  UploadIcon,
  TrashIcon,
  LinkIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "./icons";
import { useChannelRuntime, ChatMessage, DocItem } from "../hooks/useChannelRuntime";
import { useRoomFiles } from "../hooks/useRoomFiles";
import { useContradictions } from "../hooks/useContradictions";
import { RoomFile } from "../services/roomFile";
import { Contradiction, ContradictionSeverity } from "../services/contradiction";
import { uploadMeetingAudioApi } from "../services/meeting";
import { hashAvatarColor } from "../data/avatarColors";
import Avatar from "./Avatar";
import ContradictionMessage from "./ContradictionMessage";
import DocumentPreviewModal from "./DocumentPreviewModal";
import LinkExistingDocumentModal from "./LinkExistingDocumentModal";

function severityBadge(severity: ContradictionSeverity, t: any) {
  const map = {
    high: { label: t.priority_high, className: "bg-recall-danger/15 text-recall-danger" },
    medium: { label: t.priority_medium, className: "bg-amber-500/15 text-amber-400" },
    low: { label: t.priority_low, className: "bg-recall-textMuted/15 text-recall-textMuted" },
  } as const;
  const { label, className } = map[severity];
  return <span className={`flex-shrink-0 rounded-full px-1.5 py-0.5 text-[11px] ${className}`}>{label}</span>;
}

interface MainAreaProps {
  channel: Channel;
  workspaceId: string;
  currentUser: { id: string; name: string; avatarColor: string; avatarImageUrl: string | null };
  memberNameById: Record<string, string>;
  memberAvatarById: Record<string, string | null>;
  activeRecorderName: string | null;
  onOpenDecision: (decisionId: string) => void;
  t: any;
}

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

type Tab = "message" | "docs";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function formatMessageTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const hours = d.getHours();
  const period = hours < 12 ? "오전" : "오후";
  const h12 = hours % 12 === 0 ? 12 : hours % 12;
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${period} ${h12}:${mm}`;
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
            // 한글 등 조합 입력(IME) 중 Enter는 조합 확정용 키 입력이라 무시 - 안 그러면
            // Enter 한 번에 keydown이 두 번 발생해서 마지막 글자가 별도 메시지로 중복 전송됨
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
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

function ContradictionPanel({
  contradictions,
  onViewReference,
  onViewDecision,
  t,
}: {
  contradictions: Contradiction[];
  onViewReference: (fileId: string, name: string) => void;
  onViewDecision: (decisionId: string, name: string) => void;
  t: any;
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
        title={t.meeting_contradiction_list_expand}
        className="group relative flex w-8 flex-shrink-0 flex-col items-center gap-2 rounded-lg border border-recall-border bg-recall-bgSoft py-3 text-recall-textMuted transition-colors hover:border-recall-accent/40 hover:bg-white/5"
      >
        {contradictions.length > 0 && (
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-recall-accent text-[10px] font-semibold text-white">
            {contradictions.length}
          </span>
        )}
        <ChevronLeftIcon size={11} className="opacity-50 transition-opacity group-hover:opacity-100" />
      </button>
    );
  }

  return (
    <div className="flex w-64 flex-shrink-0 flex-col rounded-lg border border-recall-border bg-recall-bgSoft p-3">
      <div className="mb-2 flex items-center gap-1.5">
        <button
          onClick={() => setIsOpen(false)}
          title={t.meeting_contradiction_list_collapse}
          className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded hover:bg-white/5"
        >
          <ChevronRightIcon size={13} className="text-recall-textMuted" />
        </button>
        <p className="flex items-center gap-1.5 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
          {t.contradiction_title}
        </p>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto">
        {contradictions.length === 0 ? (
          <p className="text-sm text-recall-textMuted">{t.contradiction_none}</p>
        ) : (
          contradictions.map((c) => {
            const isExpanded = expandedIds.has(c.id);
            return (
              <div
                key={c.id}
                onClick={() => toggleExpanded(c.id)}
                className="cursor-pointer rounded-lg border border-recall-border p-2.5 hover:border-recall-accent/40"
              >
                <div className="mb-1 flex items-center justify-end">{severityBadge(c.severity, t)}</div>
                <ContradictionMessage
                  contradiction={c}
                  expanded={isExpanded}
                  onViewReference={onViewReference}
                  onViewDecision={onViewDecision}
                  t={t}
                />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function MessageTab({
  messages,
  onSend,
  onDeleteMessage,
  onUploadFiles,
  roomFiles,
  onOpenPreview,
  contradictions,
  onOpenDecision,
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
  onOpenDecision: (decisionId: string) => void;
  currentUser: MainAreaProps["currentUser"];
  memberAvatarById: Record<string, string | null>;
  t: any;
}) {
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);
  const [contextMenu, setContextMenu] = useState<{ messageId: string; x: number; y: number } | null>(null);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldScrollToBottomRef = useRef(false);

  function scrollToBottom() {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  // 메시지 전송은 서버 응답을 기다린 뒤에야 목록에 반영되므로(낙관적 업데이트 아님),
  // 전송 시점엔 스크롤 예약만 해두고 실제 스크롤은 messages가 갱신된 뒤 useEffect에서 실행한다.
  useEffect(() => {
    if (shouldScrollToBottomRef.current) {
      shouldScrollToBottomRef.current = false;
      scrollToBottom();
    }
  }, [messages]);

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
    if (text) {
      // 위로 스크롤해서 옛날 메시지 보다가 새로 채팅 치면, 방금 보낸 메시지를 바로 볼 수 있게 맨 아래로 이동
      shouldScrollToBottomRef.current = true;
      onSend(text);
    }

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
                <p className="flex items-baseline gap-1.5 text-base font-medium text-recall-text">
                  {m.author}
                  <span className="text-xs font-normal text-recall-textMuted">{formatMessageTime(m.createdAt)}</span>
                </p>
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
          <div ref={bottomRef} />
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
        onViewReference={onOpenPreview}
        onViewDecision={(decisionId) => onOpenDecision(decisionId)}
        t={t}
      />
    </div>
  );
}

function docExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toUpperCase() : "";
}

function DocsTab({
  docs,
  activeDocId,
  onUploadFiles,
  onRemoveDoc,
  onLinkExisting,
  onOpenPreview,
  t,
}: {
  docs: DocItem[];
  activeDocId: string | null;
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

      {docs.length === 0 ? (
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
      ) : (
        <div className="mb-3 flex gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 rounded-full border border-recall-border px-3 py-1.5 text-sm text-recall-text hover:bg-white/5"
          >
            <UploadIcon size={13} />
            {t.docs_tab_msg}
          </button>
          <button
            onClick={onLinkExisting}
            className="flex items-center gap-1.5 rounded-full border border-recall-border px-3 py-1.5 text-sm text-recall-textMuted hover:bg-white/5"
          >
            <LinkIcon size={13} />
            기존 문서 연결
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        {docs.map((doc) => {
          const isActive = doc.id === activeDocId;
          return (
            <div
              key={doc.id}
              onClick={() => doc.kind === "file" && onOpenPreview(doc.id, doc.name)}
              className={`group relative flex flex-col gap-2 rounded-lg border px-3 py-2.5 text-base ${
                doc.kind === "file" ? "cursor-pointer" : ""
              } ${
                isActive
                  ? "border-recall-accent bg-recall-accent/10"
                  : "border-recall-border hover:border-recall-accent/50"
              }`}
            >
              <div className="flex items-start justify-between gap-1.5">
                <span
                  className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${
                    isActive ? "bg-recall-accent/20 text-recall-accent" : "bg-recall-bgMain text-recall-textMuted"
                  }`}
                >
                  {doc.kind === "voice" ? <MicIcon size={14} /> : <DocumentIcon size={14} />}
                </span>
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemoveDoc(doc.id);
                  }}
                  className="hidden flex-shrink-0 text-recall-textMuted hover:text-recall-danger group-hover:inline"
                >
                  <CloseIcon size={13} />
                </span>
              </div>
              <p className="line-clamp-2 text-sm font-medium leading-snug text-recall-text">{doc.name}</p>
              <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-recall-textMuted">
                {doc.kind === "file" && docExtension(doc.name) && (
                  <span className="rounded border border-recall-border px-1 py-0.5 font-medium">
                    {docExtension(doc.name)}
                  </span>
                )}
                <span>{doc.statusLabel ?? formatFileSize(doc.size)}</span>
                <span className="opacity-50">·</span>
                <span>{doc.date}</span>
              </p>
            </div>
          );
        })}
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
  onOpenDecision,
  t,
}: MainAreaProps) {
  const [activeTab, setActiveTab] = useState<Tab>("message");

  const { chatMessages, sendChatMessage, deleteMessage } = useChannelRuntime(
    workspaceId,
    channel.id,
    currentUser,
    memberNameById
  );

  const roomFiles = useRoomFiles(workspaceId, channel.id);

  const { contradictions: workspaceContradictions } = useContradictions(workspaceId);

  const roomContradictions = workspaceContradictions.filter(
    (c) => c.source_type === "room_message" && c.room_message_id && chatMessages.some((m) => m.id === c.room_message_id)
  );

  const mergedDocs: DocItem[] = roomFiles.files.map((f) => ({
    id: f.id,
    name: f.original_filename,
    size: 0,
    statusLabel: analysisStatusLabel(f.analysis_status),
    date: formatDocDate(f.created_at),
    kind: "file" as const,
  }));

  async function handleUploadFromChat(files: File[], kind: "file" | "voice") {
    if (kind === "voice") {
      for (const file of files) {
        const title = file.name.replace(/\.[^./]+$/, "") || file.name;
        const res = await uploadMeetingAudioApi(workspaceId, file, title, channel.id);
        if (res.status === "success") {
          sendChatMessage(`음성 파일을 공유했습니다: ${file.name}`);
        } else {
          alert(res.message);
        }
      }
      return;
    }
    for (const file of files) {
      const ok = await roomFiles.uploadFile(file);
      if (ok) sendChatMessage(`문서를 공유했습니다: ${file.name}`);
    }
  }

  async function handleUploadFromDocsTab(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;
    for (const file of Array.from(fileList)) {
      await roomFiles.uploadFile(file);
    }
  }

  function handleRemoveDoc(id: string) {
    roomFiles.removeFile(id);
  }

  const [showLinkModal, setShowLinkModal] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<{ id: string; name: string } | null>(null);

  const tabs: { id: Tab; label: string }[] = [
    { id: "message", label: t.chat_tab_message },
    { id: "docs", label: t.chat_tab_docs },
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
                  <Avatar
                    user={{ name, avatarColor: hashAvatarColor(id), avatarImageUrl: memberAvatarById[id] ?? null }}
                    size={24}
                    className={`border-2 ${isRecording ? "border-recall-danger" : "border-recall-bgMain"}`}
                  />
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
          onOpenDecision={onOpenDecision}
          currentUser={currentUser}
          memberAvatarById={memberAvatarById}
          t={t}
        />
      )}
      {activeTab === "docs" && (
        <DocsTab
          docs={mergedDocs}
          activeDocId={previewDoc?.id ?? null}
          onUploadFiles={(fileList) => handleUploadFromDocsTab(fileList)}
          onRemoveDoc={handleRemoveDoc}
          onLinkExisting={() => setShowLinkModal(true)}
          onOpenPreview={(id, name) => setPreviewDoc({ id, name })}
          t={t}
        />
      )}

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
          t={t}
        />
      )}
    </div>
  );
}