// src/components/AiChatView.tsx
import { useEffect, useRef, useState } from "react";
import { useAiChat } from "../hooks/useAiChat";
import { SendIcon, WarningIcon, DocumentIcon, PlusIcon, TrashIcon, ChevronLeftIcon, ChevronRightIcon } from "./icons";
import DocumentPreviewModal from "./DocumentPreviewModal";

function ThinkingDots() {
  return (
    <span className="flex items-center gap-1 py-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted" />
    </span>
  );
}

function formatSessionDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export default function AiChatView({
  workspaceId,
  chat,
  t,
}: {
  workspaceId: string;
  chat: ReturnType<typeof useAiChat>;
  t: any;
}) {
  const {
    sessions,
    activeSessionId,
    selectSession,
    createSession,
    deleteSession,
    messages,
    isLoadingSessions,
    isLoadingMessages,
    isSending,
    sendMessage,
    fetchSources,
  } = chat;
  const [input, setInput] = useState("");
  const [openSourcesForId, setOpenSourcesForId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [previewDoc, setPreviewDoc] = useState<{ id: string; name: string } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldScrollToBottomRef = useRef(false);

  // 메시지 전송/응답 반영은 서버 응답을 기다린 뒤에야 목록에 나타나므로, 전송 시점엔
  // 스크롤 예약만 해두고 실제 스크롤은 messages가 갱신된 뒤 useEffect에서 실행한다.
  useEffect(() => {
    if (shouldScrollToBottomRef.current) {
      shouldScrollToBottomRef.current = false;
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  function handleSend(promptText?: string) {
    const query = promptText || input;
    if (!query.trim() || isSending) return;
    // 위로 스크롤해서 옛날 대화 보다가 새로 채팅 치면, 방금 보낸 질문을 바로 볼 수 있게 맨 아래로 이동
    shouldScrollToBottomRef.current = true;
    sendMessage(query);
    setInput("");
  }

  function handleToggleSources(messageId: string) {
    if (openSourcesForId === messageId) {
      setOpenSourcesForId(null);
    } else {
      setOpenSourcesForId(messageId);
      fetchSources(messageId);
    }
  }

  function handleDeleteSession(e: React.MouseEvent, sessionId: string) {
    e.stopPropagation();
    if (!window.confirm(t.ai_chat_delete_session_confirm)) return;
    deleteSession(sessionId);
  }

  return (
    <div className="flex h-full w-full bg-recall-bgMain text-recall-text">
      {/* 왼쪽 대화 목록 패널 */}
      {!isSidebarOpen ? (
        <button
          onClick={() => setIsSidebarOpen(true)}
          title={t.ai_chat_expand_sidebar}
          className="flex h-full w-8 flex-shrink-0 flex-col items-center justify-center gap-1.5 border-r border-recall-border text-recall-textMuted hover:bg-white/5"
        >
          <ChevronRightIcon size={13} />
        </button>
      ) : (
        <div className="flex h-full w-56 flex-shrink-0 flex-col border-r border-recall-border p-3">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-wider text-recall-textMuted">
              {t.ai_chat_session_list_title}
            </p>
            <button
              onClick={() => setIsSidebarOpen(false)}
              title={t.ai_chat_collapse_sidebar}
              className="flex h-6 w-6 items-center justify-center rounded hover:bg-white/5"
            >
              <ChevronLeftIcon size={13} className="text-recall-textMuted" />
            </button>
          </div>

          <button
            onClick={() => createSession()}
            className="mb-3 flex w-full items-center justify-center gap-1.5 rounded-xl bg-recall-accent py-2 text-xs font-bold text-white hover:opacity-90 transition"
          >
            <PlusIcon size={13} />
            <span>{t.ai_chat_new_session}</span>
          </button>

          <div className="flex-1 space-y-1 overflow-y-auto custom-scrollbar pr-0.5">
            {isLoadingSessions ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
            ) : sessions.length === 0 ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.ai_chat_no_sessions}</p>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => selectSession(s.id)}
                  className={`group flex cursor-pointer items-center justify-between gap-1 rounded-xl border p-2 transition ${
                    s.id === activeSessionId
                      ? "border-recall-accent bg-recall-accent/10"
                      : "border-recall-border/80 bg-recall-bgSoft/40 hover:bg-white/5"
                  }`}
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-recall-text">
                      {s.title || t.ai_chat_untitled_session}
                    </p>
                    <p className="text-[10px] text-recall-textMuted">{formatSessionDate(s.updated_at)}</p>
                  </div>
                  <button
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    className="hidden flex-shrink-0 text-recall-textMuted hover:text-recall-danger group-hover:inline transition"
                    aria-label={t.ai_chat_delete_session_aria}
                  >
                    <TrashIcon size={12} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* 오른쪽 대화 영역 */}
      <div className="flex h-full flex-1 flex-col p-6">
        {/* 헤더 */}
        <div className="mb-4 border-b border-recall-border pb-3">
          <h2 className="text-lg font-bold">{t.ai_chat_page_title}</h2>
          <p className="text-xs text-recall-textMuted mt-0.5">
            {t.ai_chat_page_subtitle}
          </p>
        </div>

        {/* 대화 내역 영역 */}
        <div className="flex-1 overflow-y-auto space-y-4 px-2 py-2">
          {isLoadingMessages ? (
            <p className="text-sm text-recall-textMuted">{t.common_loading}</p>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center py-8">
              <div>
                <h1 className="text-2xl font-bold text-recall-text tracking-tight">
                  {t.ai_chat_welcome_title}
                </h1>
                <p className="text-xs text-recall-textMuted mt-1.5">
                  {t.ai_chat_welcome_subtitle}
                </p>
              </div>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={`flex items-end gap-2 ${m.role === "assistant" ? "" : "flex-row-reverse"}`}
              >
                <div
                  className={`flex flex-col gap-1 ${
                    m.role === "assistant" ? "max-w-[85%] items-start" : "max-w-[80%] items-end"
                  }`}
                >
                  {m.role === "assistant" ? (
                    <div className="whitespace-pre-wrap px-1 py-1 text-sm leading-relaxed text-recall-text">
                      {m.isPending ? <ThinkingDots /> : m.content}
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap rounded-2xl rounded-br-md bg-recall-accent px-4 py-3 text-sm leading-relaxed text-white shadow-sm">
                      {m.content}
                    </div>
                  )}

                  {/* 근거자료 버튼 및 모델명 */}
                  {m.role === "assistant" && !m.isPending && !m.errorText && (
                    <div className="flex items-center gap-2 mt-0.5">
                      {m.modelName && (
                        <span className="text-[10px] text-recall-textMuted/70 uppercase">
                          {m.modelName}
                        </span>
                      )}
                      <button
                        onClick={() => handleToggleSources(m.id)}
                        className="flex items-center gap-1 text-xs text-recall-textMuted hover:text-recall-accent transition"
                      >
                        <DocumentIcon size={12} />
                        <span>{openSourcesForId === m.id ? t.ai_chat_sources_hide : t.ai_chat_sources_show}</span>
                      </button>
                    </div>
                  )}

                  {/* 근거 자료 펼침 목록 */}
                  {openSourcesForId === m.id && (
                    <div className="mt-1 w-full rounded-xl border border-recall-border bg-recall-bgMain p-3 space-y-2 text-xs">
                      <p className="font-semibold text-recall-textMuted border-b border-recall-border pb-1">
                        {t.ai_chat_sources_title}
                      </p>
                      {!m.sources ? (
                        <p className="text-recall-textMuted">{t.ai_chat_sources_loading}</p>
                      ) : m.sources.length === 0 ? (
                        <p className="text-recall-textMuted">{t.ai_chat_sources_empty}</p>
                      ) : (
                        m.sources.map((src) => {
                          const label =
                            src.source_type === "decision"
                              ? t.ai_chat_source_decision
                              : src.source_type === "content_chunk"
                              ? `${t.ai_chat_source_doc_chunk} ${src.file_name ?? ""}`
                              : `${t.ai_chat_source_code_fact} ${src.file_name ?? ""}`;
                          const isViewable = src.source_type === "content_chunk";

                          return (
                            <div key={src.id} className="flex items-center justify-between gap-2 border-b border-recall-border/50 pb-1 last:border-b-0">
                              {isViewable ? (
                                <button
                                  type="button"
                                  onClick={() => setPreviewDoc({ id: src.file_id, name: src.file_name || label })}
                                  className="truncate text-left text-recall-accent underline hover:opacity-80"
                                >
                                  {label}
                                </button>
                              ) : (
                                <span className="truncate text-recall-text">{label}</span>
                              )}
                              {src.similarity_score && (
                                <span className="text-recall-accent font-medium flex-shrink-0">
                                  {t.ai_chat_similarity_label(Math.round(src.similarity_score * 100))}
                                </span>
                              )}
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}

                  {m.errorText && (
                    <p className="flex items-center gap-1 text-xs text-recall-danger mt-1">
                      <WarningIcon size={12} /> {m.errorText}
                    </p>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        {/* 질문 입력창 */}
        <div className="relative mt-3 flex items-center gap-2 rounded-2xl border border-recall-border bg-recall-bgSoft p-2 shadow-sm">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && handleSend()}
            placeholder={t.ai_chat_input_placeholder}
            className="flex-1 bg-transparent px-3 py-2 text-sm text-recall-text placeholder:text-recall-textMuted outline-none"
          />
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || isSending}
            aria-label="Send"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl bg-recall-accent text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            <SendIcon size={14} />
          </button>
        </div>
      </div>

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
