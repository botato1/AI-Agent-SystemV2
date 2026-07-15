import { useEffect, useRef, useState } from "react";
import { Channel } from "../types";
import { SendIcon, DocumentIcon, MicIcon, PlusIcon, CloseIcon, SparklesIcon, WarningIcon, CheckIcon, UploadIcon } from "./icons";
import { useChannelRuntime, ChatMessage, DocItem } from "../hooks/useChannelRuntime";
import { mockMemberActivities } from "../data/mockData";

interface MainAreaProps {
  channel: Channel;
  activeRecorderName: string | null;
}

type Tab = "message" | "docs" | "aiChat";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

// 채팅 입력창 - "+"로 문서/음성 업로드 선택. 드래그앤드롭 대기 파일 목록은 부모(MessageTab)가 관리해서
// 화면 전체 어디에 드롭해도 여기 칩으로 쌓이게 함 (텍스트 없이 파일만 보내는 것도 가능)
function ComposerBar({
  pendingFiles,
  onAddFiles,
  onRemovePendingFile,
  onSend,
}: {
  pendingFiles: File[];
  onAddFiles: (fileList: FileList | null) => void;
  onRemovePendingFile: (index: number) => void;
  onSend: (text: string) => void;
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
    // 텍스트도 없고 대기 중인 파일도 없으면 보낼 게 없음
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
                aria-label="첨부 제거"
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
            aria-label="업로드"
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
          placeholder="메시지 보내기... (Enter로 전송)"
          rows={1}
          className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none"
        />

        <button
          onClick={handleSend}
          aria-label="보내기"
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

// 모순 감지 패널 - 메시지 탭 오른쪽에 항상 떠있는 패널 (더미 데이터, 기존유지/변경 두 버튼)
function ContradictionPanel() {
  const [resolved, setResolved] = useState<"kept" | "changed" | null>(null);

  return (
    <div className="flex w-64 flex-shrink-0 flex-col rounded-lg border border-recall-border bg-recall-bgSoft p-3">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
        <WarningIcon size={13} className="text-recall-danger" />
        모순 감지 내역
      </p>
      {resolved ? (
        <p className="flex items-center gap-1.5 text-sm text-recall-textMuted">
          <CheckIcon size={15} className="text-recall-accent" />
          {resolved === "kept" ? "기존 내용을 유지했어요." : "새 내용으로 변경했어요."}
        </p>
      ) : (
        <>
          <p className="mb-4 text-sm text-recall-text">
            지수님이 6/19에 "게이트웨이는 하나로 통합"하기로 했는데, 승주님이 방금 올린 문서엔
            "게이트웨이를 분리"하는 내용으로 되어있어요. 어느 쪽이 맞나요?
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setResolved("kept")}
              className="flex-1 rounded-lg border border-recall-border px-2 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              기존 유지
            </button>
            <button
              onClick={() => setResolved("changed")}
              className="flex-1 rounded-lg border border-recall-accent px-2 py-1.5 text-xs text-recall-accent hover:bg-recall-accent/10"
            >
              변경
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// 메시지 탭: 왼쪽엔 팀원별 최근 활동 + 실제 채팅 내역, 오른쪽엔 모순 감지 패널
// 화면 전체(이 탭 영역) 어디에 파일을 끌어다 놓아도 감지해서 오버레이 + 대기 칩으로 쌓임
function MessageTab({
  messages,
  onSend,
  onUploadFiles,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  onUploadFiles: (files: File[], kind: "file" | "voice") => void;
}) {
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);

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
      // mime 타입으로 문서/음성 자동 구분해서 각각 올림
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
          <p className="text-base font-medium text-recall-text">파일을 올려두세요</p>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-3 overflow-y-auto">
         {mockMemberActivities.map((activity) =>
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
        />
      </div>

      <ContradictionPanel />
    </div>
  );
}

// 문서보관함 탭: 문서/음성 파일 목록 (채팅 "+"로 올린 것도 여기 같이 보임)
// 화면 전체 어디에 파일을 끌어다 놓아도 감지해서 오버레이가 뜸
function DocsTab({
  docs,
  onUploadFiles,
  onRemoveDoc,
}: {
  docs: DocItem[];
  onUploadFiles: (fileList: FileList | null, kind: "file" | "voice") => void;
  onRemoveDoc: (id: string) => void;
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
          <p className="text-base font-medium text-recall-text">파일을 올려두세요</p>
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
        <p className="text-sm text-recall-text">파일을 끌어다 놓거나 클릭해서 선택하세요</p>
        <p className="mt-1 text-xs text-recall-textMuted">PDF, DOCX, 이미지 등</p>
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

// AI Chat 탭: 이 채팅방(메시지+문서)을 참고해서 답하는 AI, 전체 탭 하나를 다 씀
function AiChatTab() {
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
          text: "이 채팅방의 메시지·문서를 참고해서 답할게요. (지금은 더미 답변이에요, API 연동 전)",
        },
      ]);
      setIsThinking(false);
    }, 900);
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="flex-1 space-y-2 overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-sm text-recall-textMuted">이 채팅방 내용에 대해 뭐든 물어보세요.</p>
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
        {isThinking && <p className="text-xs text-recall-textMuted">답변 작성 중...</p>}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="궁금한 점을 입력하세요"
          className="flex-1 rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none focus:border-recall-accent"
        />
        <button
          onClick={handleSend}
          aria-label="전송"
          className="flex flex-shrink-0 items-center justify-center rounded-lg border border-recall-border px-3 py-2 text-sm text-recall-text hover:bg-white/5"
        >
          <SendIcon size={14} />
        </button>
      </div>
    </div>
  );
}

export default function MainArea({ channel, activeRecorderName }: MainAreaProps) {
  const [activeTab, setActiveTab] = useState<Tab>("message");

  // 채널 id 단위로 독립적인 채팅/문서 상태 (다른 채널로 넘어가도 안 섞이고, 돌아오면 그대로 이어짐)
  const { chatMessages, docs, sendChatMessage, addDocFiles, removeDoc } = useChannelRuntime(channel.id);

  const tabs: { id: Tab; label: string }[] = [
    { id: "message", label: "메시지" },
    { id: "docs", label: "문서보관함" },
    { id: "aiChat", label: "AI" },
  ];

  // 참여 중인 팀원 아바타 - 더미
  const participants = ["지수", "나연", "승주", "동현"];

  return (
    <div className="flex h-full flex-1 flex-col bg-recall-bgMain p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="truncate text-[13px] font-medium text-recall-text">{channel.name}</p>
        <div className="flex items-center gap-1">
          <div className="flex -space-x-1.5">
            {participants.map((name) => {
              const isRecording = name === activeRecorderName;
              return (
                <div key={name} title={isRecording ? `${name} · 녹음 중` : name} className="relative">
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
        />
      )}
      {activeTab === "docs" && (
        <DocsTab
          docs={docs}
          onUploadFiles={(files, kind) => addDocFiles(files, kind, false)}
          onRemoveDoc={removeDoc}
        />
      )}
      {activeTab === "aiChat" && <AiChatTab />}
    </div>
  );
}