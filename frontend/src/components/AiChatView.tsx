// src/components/AiChatView.tsx
import { useEffect, useRef, useState } from "react";
import { useAiChat } from "../hooks/useAiChat";
import {
  SendIcon,
  WarningIcon,
  DocumentIcon,
  PlusIcon,
  TrashIcon,
  MoreIcon,
  PencilIcon,
  PinIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "./icons";
import DocumentPreviewModal from "./DocumentPreviewModal";
import { Category } from "../services/category";
import { getCategoryColor } from "../utils/categoryColor";
import CategoryBadge from "./CategoryBadge";

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

function isSameDay(a: string, b: string): boolean {
  const da = new Date(a);
  const db = new Date(b);
  return (
    da.getFullYear() === db.getFullYear() &&
    da.getMonth() === db.getMonth() &&
    da.getDate() === db.getDate()
  );
}

function formatDateDivider(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "short" });
}

function DateDivider({ iso }: { iso: string }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="h-px flex-1 bg-recall-border" />
      <span className="flex-shrink-0 text-[11px] font-medium text-recall-textMuted">
        {formatDateDivider(iso)}
      </span>
      <div className="h-px flex-1 bg-recall-border" />
    </div>
  );
}

export default function AiChatView({
  workspaceId,
  chat,
  categories,
  selectedCategoryId,
  t,
}: {
  workspaceId: string;
  chat: ReturnType<typeof useAiChat>;
  categories: Category[];
  selectedCategoryId: string | null;
  t: any;
}) {
  const {
    sessions,
    activeSessionId,
    selectSession,
    startNewChat,
    renameSession,
    togglePinSession,
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
  const [openSessionMenuId, setOpenSessionMenuId] = useState<string | null>(null);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [sessionDraftTitle, setSessionDraftTitle] = useState("");
  const sessionMenuRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastMessageIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!openSessionMenuId) return;
    function handleClickOutside(e: MouseEvent) {
      if (sessionMenuRef.current && !sessionMenuRef.current.contains(e.target as Node)) {
        setOpenSessionMenuId(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [openSessionMenuId]);

  // 사이드바 전역 카테고리 선택기 - null("전체")이면 전부. 카테고리 지원 배포 이전에 생긴
  // 세션은 category_id가 null이라, "기본" 카테고리를 선택했을 때는 그것도 같이 보여준다
  // (안 그러면 예전 대화들이 어느 카테고리를 선택해도 영영 안 보이게 된다).
  const defaultCategory = categories.find((c) => c.is_default) ?? null;
  const visibleSessions = !selectedCategoryId
    ? sessions
    : sessions.filter(
        (s) =>
          s.category_id === selectedCategoryId ||
          (!s.category_id && defaultCategory?.id === selectedCategoryId)
      );

  // 다른 대화로 전환하거나 새 대화를 만들면, 지금 입력창에 쳐뒀지만 안 보낸 글자는
  // 그 대화만의 임시 메모가 아니라 그냥 버려져야 한다 - 안 그러면 A 대화에 쓰다 만
  // 문장이 B 대화로 넘어가서도 그대로 남아있는 버그가 생긴다.
  useEffect(() => {
    setInput("");
  }, [activeSessionId]);

  // 새 메시지가 추가되면, 그게 "내가 방금 보낸 것"(사용자 메시지 또는 응답 대기 중인
  // pending 자리표시자)일 때만 바닥으로 스크롤한다. 이 자리를 채우는 실제 답변이 나중에
  // 도착해도 메시지 id는 그대로라 다시 스크롤하진 않는다(이미 바닥에 있었으므로).
  //
  // 예전엔 handleSend()에서 1회성 플래그(shouldScrollToBottomRef)를 세워뒀다가 messages가
  // 바뀔 때 소비했는데, sources 조회 등 전송과 무관한 다른 setMessages 호출이 그 사이에
  // 끼어들면 플래그가 엉뚱하게 먼저 소비돼버릴 수 있었다. 메시지 자체의 속성으로 판단하면
  // 그런 경쟁 상태가 생기지 않는다.
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!last || last.id === lastMessageIdRef.current) return;
    lastMessageIdRef.current = last.id;

    if (last.role === "user" || last.isPending) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  function handleSend(promptText?: string) {
    const query = promptText || input;
    if (!query.trim() || isSending) return;
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

  function handleDeleteSession(sessionId: string) {
    setOpenSessionMenuId(null);
    if (!window.confirm(t.ai_chat_delete_session_confirm)) return;
    deleteSession(sessionId);
  }

  function startRenameSession(s: { id: string; title: string | null }) {
    setEditingSessionId(s.id);
    setSessionDraftTitle(s.title || "");
    setOpenSessionMenuId(null);
  }

  function commitRenameSession() {
    if (editingSessionId && sessionDraftTitle.trim()) {
      renameSession(editingSessionId, sessionDraftTitle.trim());
    }
    setEditingSessionId(null);
  }

  function handleTogglePin(s: { id: string; is_pinned: boolean }) {
    setOpenSessionMenuId(null);
    togglePinSession(s.id, !s.is_pinned);
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
            onClick={() => startNewChat(selectedCategoryId ?? undefined)}
            className="mb-3 flex w-full items-center justify-center gap-1.5 rounded-xl bg-recall-accent py-2 text-xs font-bold text-white hover:opacity-90 transition"
          >
            <PlusIcon size={13} />
            <span>{t.ai_chat_new_session}</span>
          </button>

          <div className="flex-1 space-y-1 overflow-y-auto custom-scrollbar pr-0.5">
            {isLoadingSessions ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
            ) : visibleSessions.length === 0 ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.ai_chat_no_sessions}</p>
            ) : (
              visibleSessions.map((s) => {
                const categoryIndex = categories.findIndex((c) => c.id === s.category_id);
                const cat = categoryIndex >= 0 ? categories[categoryIndex] : null;
                return (
                  <div
                    key={s.id}
                    onClick={() => selectSession(s.id)}
                    className={`group relative flex cursor-pointer items-center justify-between gap-1 rounded-xl border p-2 transition ${
                      s.id === activeSessionId
                        ? "border-recall-accent bg-recall-accent/10"
                        : "border-recall-border/80 bg-recall-bgSoft/40 hover:bg-white/5"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      {editingSessionId === s.id ? (
                        <input
                          autoFocus
                          value={sessionDraftTitle}
                          onChange={(e) => setSessionDraftTitle(e.target.value)}
                          onFocus={(e) => e.target.select()}
                          onClick={(e) => e.stopPropagation()}
                          onBlur={commitRenameSession}
                          onKeyDown={(e) => e.key === "Enter" && commitRenameSession()}
                          className="w-full rounded border border-recall-border bg-transparent px-1 py-0.5 text-xs font-semibold text-recall-text outline-none focus:border-recall-accent"
                        />
                      ) : (
                        <p className="flex items-center gap-1 truncate text-xs font-semibold text-recall-text">
                          {s.is_pinned && <PinIcon size={10} className="flex-shrink-0 fill-current text-recall-accent" />}
                          <span className="truncate">{s.title || t.ai_chat_untitled_session}</span>
                        </p>
                      )}
                      <div className="flex items-center gap-1.5">
                        <p className="text-[10px] text-recall-textMuted">{formatSessionDate(s.updated_at)}</p>
                        {cat && !cat.is_default && (
                          <CategoryBadge
                            name={cat.name}
                            color={getCategoryColor(categoryIndex)}
                            className="!py-0 !text-[10px]"
                          />
                        )}
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenSessionMenuId((prev) => (prev === s.id ? null : s.id));
                      }}
                      className={`flex-shrink-0 rounded p-0.5 text-recall-textMuted transition hover:bg-white/10 hover:text-recall-text ${
                        openSessionMenuId === s.id ? "inline" : "hidden group-hover:inline"
                      }`}
                      aria-label="대화 메뉴"
                    >
                      <MoreIcon size={14} />
                    </button>

                    {openSessionMenuId === s.id && (
                      <div
                        ref={sessionMenuRef}
                        onClick={(e) => e.stopPropagation()}
                        className="absolute right-1 top-9 z-20 w-28 rounded-lg border border-recall-border bg-recall-bgSoft p-1 shadow-lg"
                      >
                        <button
                          onClick={() => startRenameSession(s)}
                          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs text-recall-text hover:bg-white/5"
                        >
                          <PencilIcon size={12} />
                          이름변경
                        </button>
                        <button
                          onClick={() => handleTogglePin(s)}
                          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs text-recall-text hover:bg-white/5"
                        >
                          <PinIcon size={12} />
                          {s.is_pinned ? "고정 해제" : "고정"}
                        </button>
                        <button
                          onClick={() => handleDeleteSession(s.id)}
                          className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-xs text-recall-danger hover:bg-white/5"
                        >
                          <TrashIcon size={12} />
                          삭제
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
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
        <div className="flex-1 overflow-y-auto space-y-3 px-2 py-2">
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
            messages.map((m, idx) => {
              const prev = messages[idx - 1];
              const showDateDivider =
                !!m.createdAt && (!prev?.createdAt || !isSameDay(prev.createdAt, m.createdAt));
              return (
              <div key={m.id}>
              {showDateDivider && <DateDivider iso={m.createdAt!} />}
              <div
                className={`flex items-end gap-2 ${m.role === "assistant" ? "" : "flex-row-reverse"}`}
              >
                <div
                  className={`flex flex-col gap-1 ${
                    m.role === "assistant" ? "max-w-[85%] items-start" : "max-w-[80%] items-end"
                  }`}
                >
                  {m.role === "assistant" ? (
                    <div className="whitespace-pre-wrap px-0.5 py-1 text-[15px] leading-relaxed text-recall-text">
                      {m.isPending ? <ThinkingDots /> : m.content}
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap rounded-2xl border border-recall-border bg-recall-bgSoft px-4 py-3 text-[15px] leading-relaxed text-recall-text shadow-sm">
                      {m.content}
                    </div>
                  )}

                  {/* 근거자료 보기 버튼 - 근거자료가 하나도 없는 답변은 버튼 자체를 숨긴다.
                      sources는 대화 로드 시 메시지마다 미리 불러와둔다 (useAiChat 참고) */}
                  {m.role === "assistant" && !m.isPending && !m.errorText && !!m.sources?.length && (
                    <div className="flex items-center gap-2 mt-0.5">
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
              </div>
              );
            })
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
