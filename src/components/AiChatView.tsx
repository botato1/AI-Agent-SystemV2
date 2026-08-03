// src/components/AiChatView.tsx
import { useState } from "react";
import { useAiChat } from "../hooks/useAiChat";
import { SendIcon, WarningIcon, DocumentIcon } from "./icons";

function ThinkingDots() {
  return (
    <span className="flex items-center gap-1 py-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-recall-textMuted" />
    </span>
  );
}

export default function AiChatView({ workspaceId, t }: { workspaceId: string; t: any }) {
  const { messages, isLoading, isSending, sendMessage, fetchSources } = useAiChat(workspaceId);
  const [input, setInput] = useState("");
  const [openSourcesForId, setOpenSourcesForId] = useState<string | null>(null);

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

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain p-6 text-recall-text">
      {/* 헤더 */}
      <div className="mb-4 border-b border-recall-border pb-3">
        <h2 className="text-lg font-bold">AI 인사이트</h2>
        <p className="text-xs text-recall-textMuted mt-0.5">
          워크스페이스의 문서와 회의 교차 분석 기반 질문 검색
        </p>
      </div>

      {/* 대화 내역 영역 */}
      <div className="flex-1 overflow-y-auto space-y-4 px-2 py-2">
        {isLoading ? (
          <p className="text-sm text-recall-textMuted">{t.common_loading}</p>
        ) : messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center py-8">
            <div>
              <h1 className="text-2xl font-bold text-recall-text tracking-tight">
                무엇을 도와드릴까요?
              </h1>
              <p className="text-xs text-recall-textMuted mt-1.5">
                회의록 분석, 업무 정리, 일정 관리 등 무엇이든 물어보세요
              </p>
            </div>
          </div>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={`flex items-end gap-2 ${m.role === "assistant" ? "" : "flex-row-reverse"}`}
            >
              <div className={`flex max-w-[80%] flex-col gap-1 ${m.role === "assistant" ? "items-start" : "items-end"}`}>
                <div
                  className={`whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                    m.role === "assistant"
                      ? "rounded-bl-md bg-recall-bgSoft text-recall-text border border-recall-border"
                      : "rounded-br-md bg-recall-accent text-white"
                  }`}
                >
                  {m.isPending ? <ThinkingDots /> : m.content}
                </div>

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
                      <span>{openSourcesForId === m.id ? "근거자료 접기" : "근거자료 보기"}</span>
                    </button>
                  </div>
                )}

                {/* 근거 자료 펼침 목록 */}
                {openSourcesForId === m.id && (
                  <div className="mt-1 w-full rounded-xl border border-recall-border bg-recall-bgMain p-3 space-y-2 text-xs">
                    <p className="font-semibold text-recall-textMuted border-b border-recall-border pb-1">
                      참고한 근거자료
                    </p>
                    {!m.sources ? (
                      <p className="text-recall-textMuted">근거자료를 불러오는 중...</p>
                    ) : m.sources.length === 0 ? (
                      <p className="text-recall-textMuted">연결된 근거자료가 없습니다.</p>
                    ) : (
                      m.sources.map((src) => (
                        <div key={src.id} className="flex items-center justify-between gap-2 border-b border-recall-border/50 pb-1 last:border-b-0">
                          <span className="truncate text-recall-text">
                            {src.source_type === "content_chunk" ? "📄 문서 청크" : "💻 코드 정보"} (파일 ID: {src.file_id.slice(0, 8)}...)
                          </span>
                          {src.similarity_score && (
                            <span className="text-recall-accent font-medium flex-shrink-0">
                              유사도 {Math.round(src.similarity_score * 100)}%
                            </span>
                          )}
                        </div>
                      ))
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
      </div>

      {/* 질문 입력창 */}
      <div className="relative mt-3 flex items-center gap-2 rounded-2xl border border-recall-border bg-recall-bgSoft p-2 shadow-sm">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && handleSend()}
          placeholder="워크스페이스 내용에 대해 질문하세요..."
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
  );
}