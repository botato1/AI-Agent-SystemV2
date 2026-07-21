// src/components/MainArea.tsx
import { useEffect, useRef, useState } from "react";
import { Channel, MemberActivity } from "../types"; // types.ts에서 정식 MemberActivity 타입을 가져옴 (충돌 해결!)
import { SendIcon, DocumentIcon, MicIcon, PlusIcon, CloseIcon, SparklesIcon, WarningIcon, CheckIcon, UploadIcon } from "./icons";
import { useChannelRuntime, ChatMessage, DocItem } from "../hooks/useChannelRuntime";

interface MainAreaProps {
  channel: Channel;
  activeRecorderName: string | null;
  t: any; // 번역 객체 타입
}

type Tab = "message" | "docs" | "aiChat";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
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
              className="flex items-center gap-1.5 rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1 text-xs text-recall-text"
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
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-recall-text hover:bg-white/5"
              >
                <DocumentIcon size={14} />
                문서 업로드
              </button>
              <button
                onClick={() => {
                  setIsMenuOpen(false);
                  voiceInputRef.current?.click();
                }}
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-recall-text hover:bg-white/5"
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
          className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none"
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

// 모순 감지 패널
function ContradictionPanel({ t }: { t: any }) {
  const [resolved, setResolved] = useState<"kept" | "changed" | null>(null);

  return (
    <div className="flex w-64 flex-shrink-0 flex-col rounded-lg border border-recall-border bg-recall-bgSoft p-3">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
        <WarningIcon size={13} className="text-recall-danger" />
        {t.dashboard_contradiction_title}
      </p>
      {resolved ? (
        <p className="flex items-center gap-1.5 text-sm text-recall-textMuted">
          <CheckIcon size={15} className="text-recall-accent" />
          {resolved === "kept" ? t.contradiction_resolved_kept : t.contradiction_resolved_changed}
        </p>
      ) : (
        <>
          <p className="mb-4 text-sm text-recall-text">
            {t.contradiction_panel_desc}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setResolved("kept")}
              className="flex-1 rounded-lg border border-recall-border px-2 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              {t.contradiction_btn_keep}
            </button>
            <button
              onClick={() => setResolved("changed")}
              className="flex-1 rounded-lg border border-recall-accent px-2 py-1.5 text-xs text-recall-accent hover:bg-recall-accent/10"
            >
              {t.contradiction_btn_change}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// 메시지 탭
function MessageTab({
  messages,
  onSend,
  onUploadFiles,
  t,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  onUploadFiles: (files: File[], kind: "file" | "voice") => void;
  t: any;
}) {
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);

  const memberActivities: MemberActivity[] = t.mock_member_activities || [];

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
          <p className="text-base font-medium text-recall-text">{t.drop_overlay}</p>
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
                <p className="text-sm text-recall-text">{activity.preview}</p>
              </div>
            ) : (
              <div key={activity.name} className="flex gap-2">
                <div className="h-7 w-7 flex-shrink-0 rounded-full bg-recall-accent/30" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-recall-text">{activity.name}</p>
                  <p className="flex items-center gap-1 truncate text-sm text-recall-textMuted">
                    {activity.kind === "upload" && <DocumentIcon size={13} className="flex-shrink-0" />}
                    {activity.preview}
                  </p>
                </div>
              </div>
            )
          )}

          {messages.map((m) => (
            <div key={m.id} className="flex gap-2">
              <div className="h-7 w-7 flex-shrink-0 rounded-full bg-recall-accent/30" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-recall-text">{m.author}</p>
                <p className="text-sm text-recall-textMuted">{m.text}</p>
              </div>
            </div>
          ))}
        </div>

        <ComposerBar
          pendingFiles={pendingFiles}
          onAddFiles={addPendingFiles}
          onRemovePendingFile={removePendingFile}
          onSend={handleSend}
          t={t}
        />
      </div>

      <ContradictionPanel t={t} />
    </div>
  );
}

// 문서보관함 탭
function DocsTab({
  docs,
  onUploadFiles,
  onRemoveDoc,
  t,
}: {
  docs: DocItem[];
  onUploadFiles: (fileList: FileList | null, kind: "file" | "voice") => void;
  onRemoveDoc: (id: string) => void;
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
          <p className="text-base font-medium text-recall-text">{t.drop_overlay}</p>
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

      <button
        onClick={() => fileInputRef.current?.click()}
        className="mb-3 flex flex-col items-center justify-center rounded-lg border border-dashed border-recall-border px-3 py-6 text-center hover:bg-white/5"
      >
        <p className="text-sm text-recall-text">{t.docs_tab_msg}</p>
        <p className="mt-1 text-xs text-recall-textMuted">{t.docs_tab_sub}</p>
      </button>

      <div className="space-y-2">
        {docs.map((doc) => (
          <div
            key={doc.id}
            className="group flex items-center justify-between rounded-lg border border-recall-border px-3 py-2 text-sm"
          >
            <span className="flex min-w-0 items-center gap-2 text-recall-text">
              <span className="flex-shrink-0 text-recall-textMuted">
                {doc.kind === "voice" ? <MicIcon size={15} /> : <DocumentIcon size={15} />}
              </span>
              <span className="truncate">{doc.name}</span>
            </span>
            <span className="flex flex-shrink-0 items-center gap-2 text-xs text-recall-textMuted">
              {formatFileSize(doc.size)} · {doc.date}
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

interface AiMessage {
  id: string;
  from: "user" | "ai";
  text: string;
}

// AI Chat 탭
function AiChatTab({ t }: { t: any }) {
  const [messages, setMessages] = useState<AiMessage[]>([]);
  const [input, setInput] = useState("");
  const [isThinking, setIsThinking] = useState(false);

  function handleSend() {
    if (!input.trim()) return;
    const question = input;
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), from: "user", text: question }]);
    setInput("");
    setIsThinking(true);
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          from: "ai",
          text: t.ai_chat_dummy_answer,
        },
      ]);
      setIsThinking(false);
    }, 900);
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex-1 space-y-2 overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-sm text-recall-textMuted">{t.ai_chat_welcome}</p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
              m.from === "ai"
                ? "bg-recall-bgSoft text-recall-text"
                : "ml-auto bg-recall-accent/20 text-recall-text"
            }`}
          >
            {m.text}
          </div>
        ))}
        {isThinking && <p className="text-xs text-recall-textMuted">{t.ai_chat_thinking}</p>}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder={t.ai_input_placeholder}
          className="flex-1 rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
        />
        <button
          onClick={handleSend}
          aria-label="Send"
          className="flex flex-shrink-0 items-center justify-center rounded-lg border border-recall-border px-3 py-2 text-sm text-recall-text hover:bg-white/5"
        >
          <SendIcon size={14} />
        </button>
      </div>
    </div>
  );
}

export default function MainArea({ channel, activeRecorderName, t }: MainAreaProps) {
  const [activeTab, setActiveTab] = useState<Tab>("message");

  const { chatMessages, docs, sendChatMessage, addDocFiles, removeDoc } = useChannelRuntime(channel.id);

  const tabs: { id: Tab; label: string }[] = [
    { id: "message", label: t.chat_tab_message },
    { id: "docs", label: t.chat_tab_docs },
    { id: "aiChat", label: t.chat_tab_ai },
  ];

  const participants = [t.name_jisu, t.name_nayeon, t.name_seungju, t.name_donghyun];

  return (
    <div className="flex h-full flex-1 flex-col bg-recall-bgMain p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="truncate text-[13px] font-medium text-recall-text">{channel.name}</p>
        <div className="flex items-center gap-1">
          <div className="flex -space-x-1.5">
            {participants.map((name) => {
              const isRecording = name === activeRecorderName;
              return (
                <div key={name} title={isRecording ? `${name} · ${t.sidebar_recording}` : name} className="relative">
                  <div
                    className={`h-6 w-6 flex-shrink-0 rounded-full border-2 bg-recall-accent/40 ${
                      isRecording ? "border-recall-danger" : "border-recall-bgMain"
                    }`}
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
          <span className="ml-1 text-xs text-recall-textMuted">{participants.length}</span>
        </div>
      </div>

      <div className="mb-2 flex gap-0.5 border-b border-recall-border">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-2 py-1 text-xs ${
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
          onUploadFiles={(files, kind) => addDocFiles(files, kind, true)}
          t={t}
        />
      )}
      {activeTab === "docs" && (
        <DocsTab
          docs={docs}
          onUploadFiles={(files, kind) => addDocFiles(files, kind, false)}
          onRemoveDoc={removeDoc}
          t={t}
        />
      )}
      {activeTab === "aiChat" && <AiChatTab t={t} />}
    </div>
  );
}