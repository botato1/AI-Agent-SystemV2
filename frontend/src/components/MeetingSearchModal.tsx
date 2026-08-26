// src/components/MeetingSearchModal.tsx
import { useState, useEffect } from "react";
import { searchMeetingsApi, RecentMeetingItem } from "../services/meeting";
import { CloseIcon, SearchIcon, PersonIcon, CalendarIcon } from "./icons";

interface MeetingSearchModalProps {
  workspaceId: string;
  onClose: () => void;
  onSelectMeeting: (meetingId: string) => void;
  t: any;
}

function formatShortDate(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

export default function MeetingSearchModal({
  workspaceId,
  onClose,
  onSelectMeeting,
  t,
}: MeetingSearchModalProps) {
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [results, setResults] = useState<RecentMeetingItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  // 디바운스를 적용해 실시간 검색 지원
  useEffect(() => {
    const timer = setTimeout(() => {
      handleSearch();
    }, 300);
    return () => clearTimeout(timer);
  }, [query, dateFrom, dateTo]);

  async function handleSearch() {
    setIsLoading(true);
    const res = await searchMeetingsApi(workspaceId, {
      q: query.trim() || undefined,
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo + "T23:59:59").toISOString() : undefined,
    });
    setIsLoading(false);

    if (res.status === "success") {
      setResults(res.meetings);
      setTotalCount(res.total_count);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="flex h-[80vh] w-full max-w-2xl flex-col rounded-2xl border border-recall-border bg-recall-bg p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 */}
        <div className="mb-4 flex items-center justify-between border-b border-recall-border pb-3">
          <div className="flex items-center gap-2">
            <SearchIcon size={20} className="text-recall-accent" />
            <h3 className="text-lg font-bold">{t.meeting_search_title}</h3>
          </div>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text transition">
            <CloseIcon size={18} />
          </button>
        </div>

        {/* 검색 필터 영역 */}
        <div className="space-y-3 mb-4">
          {/* 검색어 입력 */}
          <div className="relative flex items-center">
            <SearchIcon size={16} className="absolute left-3.5 text-recall-textMuted" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t.meeting_search_placeholder}
              className="w-full rounded-xl border border-recall-border bg-recall-bgSoft pl-10 pr-4 py-2.5 text-sm text-recall-text outline-none focus:border-recall-accent transition"
            />
          </div>

          {/* 날짜 범위 선택 */}
          <div className="flex items-center gap-2 text-xs text-recall-textMuted">
            <CalendarIcon size={14} className="flex-shrink-0" />
            <span>{t.meeting_search_date_range_label}</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-1 text-recall-text outline-none"
            />
            <span>~</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-1 text-recall-text outline-none"
            />
            {(dateFrom || dateTo) && (
              <button
                onClick={() => {
                  setDateFrom("");
                  setDateTo("");
                }}
                className="text-recall-accent hover:underline ml-1"
              >
                {t.meeting_search_reset}
              </button>
            )}
          </div>
        </div>

        {/* 검색 결과 목록 */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-2.5">
          {isLoading ? (
            <p className="py-12 text-center text-sm text-recall-textMuted">{t.meeting_search_loading}</p>
          ) : results.length === 0 ? (
            <div className="py-12 text-center text-recall-textMuted">
              <p className="text-sm font-medium">{t.meeting_search_no_results}</p>
              <p className="text-xs mt-1">{t.meeting_search_no_results_hint}</p>
            </div>
          ) : (
            results.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  onSelectMeeting(m.id);
                  onClose();
                }}
                className="flex w-full flex-col gap-1.5 rounded-xl border border-recall-border/70 bg-recall-bgSoft p-4 text-left hover:border-recall-accent/60 transition group"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-base font-bold text-recall-text group-hover:text-recall-accent transition">
                    {m.title}
                  </span>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {m.contradiction_count === 0 ? (
                      <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-400">
                        {t.home_recent_clean_badge}
                      </span>
                    ) : (
                      <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-400">
                        {t.home_recent_contradiction_badge(m.contradiction_count)}
                      </span>
                    )}
                    <span className="text-xs text-recall-textMuted">
                      {formatShortDate(m.started_at)}
                    </span>
                  </div>
                </div>

                {m.preview && (
                  <p className="line-clamp-2 text-xs text-recall-textMuted/90 leading-relaxed">
                    {m.preview}
                  </p>
                )}

                <div className="flex items-center gap-1 text-xs text-recall-textMuted mt-1">
                  <PersonIcon size={12} />
                  <span>{t.home_recent_attendee_count(m.attendee_count)}</span>
                </div>
              </button>
            ))
          )}
        </div>

        {/* 하단 요약 개수 */}
        <div className="mt-3 border-t border-recall-border pt-3 text-right text-xs text-recall-textMuted">
          {t.meeting_search_total_count(totalCount)}
        </div>
      </div>
    </div>
  );
}