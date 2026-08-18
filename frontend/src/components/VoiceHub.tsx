import { useEffect, useState } from "react";
import { Recording, getElapsedMs } from "../hooks/useCategoryRecordings";
import { FAKE_STT_LINES, STT_LINE_INTERVAL_SECONDS } from "../data/fakeMeetingData";

interface VoiceHubProps {
  categoryName: string;
  recordings: Recording[];
  activeRecordingId: string | null;
  onStartNew: () => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onStop: (id: string) => void;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const ss = String(totalSeconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function statusLabel(status: Recording["status"]): string {
  if (status === "recording") return "녹음 중";
  if (status === "paused") return "일시정지";
  return "종료됨";
}

// 오른쪽 녹음 목록 패널
function RecordingListPanel({
  recordings,
  activeRecordingId,
  onSelect,
  onRename,
}: {
  recordings: Recording[];
  activeRecordingId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
}) {
  const [, setTick] = useState(0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");

  useEffect(() => {
    const hasLiveRecording = recordings.some((r) => r.status !== "ended");
    if (!hasLiveRecording) return;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [recordings]);

  function commitRename(id: string) {
    setEditingId(null);
    if (draftName.trim()) onRename(id, draftName.trim());
  }

  return (
    <div className="flex h-full w-64 flex-shrink-0 flex-col border-l border-recall-border bg-recall-bgSoft p-4">
      <p className="mb-3 text-xs font-bold uppercase tracking-wider text-recall-textMuted">
        녹음 히스토리
      </p>
      <div className="flex-1 space-y-2 overflow-y-auto custom-scrollbar pr-0.5">
        {recordings.length === 0 ? (
          <p className="py-6 text-center text-xs text-recall-textMuted">아직 진행된 녹음이 없습니다.</p>
        ) : (
          recordings.map((r) => {
            const isSelected = r.id === activeRecordingId;
            return (
              <div
                key={r.id}
                onClick={() => onSelect(r.id)}
                className={`group flex cursor-pointer flex-col gap-1 rounded-xl border p-3 transition ${
                  isSelected
                    ? "border-recall-accent bg-recall-accent/10 shadow-sm"
                    : "border-recall-border bg-recall-bg/50 hover:bg-white/5"
                }`}
              >
                <div className="flex items-center gap-2">
                  {r.status === "recording" && (
                    <span className="h-2 w-2 flex-shrink-0 animate-pulse rounded-full bg-red-500" />
                  )}
                  {r.status === "paused" && (
                    <span className="h-2 w-2 flex-shrink-0 rounded-full bg-amber-400" />
                  )}
                  {editingId === r.id ? (
                    <input
                      autoFocus
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onBlur={() => commitRename(r.id)}
                      onKeyDown={(e) => e.key === "Enter" && commitRename(r.id)}
                      className="min-w-0 flex-1 rounded-lg border border-recall-accent bg-transparent px-1.5 py-0.5 text-xs text-recall-text focus:outline-none"
                    />
                  ) : (
                    <span className="truncate text-xs font-bold text-recall-text">{r.name}</span>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingId(r.id);
                      setDraftName(r.name);
                    }}
                    className="ml-auto hidden flex-shrink-0 text-recall-textMuted hover:text-recall-text group-hover:inline transition text-xs"
                    aria-label="이름 변경"
                  >
                    ✎
                  </button>
                </div>
                <span className="text-[11px] font-medium text-recall-textMuted">
                  {statusLabel(r.status)} · {formatDuration(getElapsedMs(r))}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

type SummaryTab = "script" | "summary";

const SUMMARY_TABS: { id: SummaryTab; label: string }[] = [
  { id: "script", label: "스크립트" },
  { id: "summary", label: "요약" },
];

function RecordingDetail({
  recording,
  onPause,
  onResume,
  onStop,
}: {
  recording: Recording;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}) {
  const [, setTick] = useState(0);
  const [summaryTab, setSummaryTab] = useState<SummaryTab>("script");

  useEffect(() => {
    if (recording.status !== "recording") return;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [recording.status]);

  const elapsedMs = getElapsedMs(recording);
  const elapsedSeconds = elapsedMs / 1000;
  const revealedCount = Math.min(
    FAKE_STT_LINES.length,
    Math.floor(elapsedSeconds / STT_LINE_INTERVAL_SECONDS)
  );
  const lines = FAKE_STT_LINES.slice(0, revealedCount);

  return (
    <div className="flex h-full flex-1 flex-col p-6 overflow-hidden">
      <div className="mb-5 flex items-center justify-between pb-4 border-b border-recall-border/60">
        <div>
          <div className="flex items-center gap-2">
            {recording.status === "recording" && (
              <>
                <span className="h-2.5 w-2.5 rounded-full bg-red-500 animate-pulse" />
                <span className="text-xs font-bold text-red-500 uppercase tracking-wider">
                  REC · Live Meeting
                </span>
              </>
            )}
            {recording.status === "paused" && (
              <span className="text-xs font-bold text-amber-400 uppercase tracking-wider">
                PAUSED
              </span>
            )}
            {recording.status === "ended" && (
              <span className="text-xs font-bold text-recall-textMuted uppercase tracking-wider">
                FINISHED
              </span>
            )}
          </div>
          <h2 className="text-xl font-bold text-recall-text mt-1">{recording.name}</h2>
          <p className="text-xs font-medium text-recall-textMuted mt-0.5">
            경과 시간: {formatDuration(elapsedMs)}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {recording.status === "recording" && (
            <button
              onClick={onPause}
              className="rounded-full border border-recall-border bg-white/5 px-4 py-2 text-xs font-semibold text-recall-text hover:bg-white/10 transition"
            >
              ❚❚ 일시정지
            </button>
          )}
          {recording.status === "paused" && (
            <button
              onClick={onResume}
              className="rounded-full border border-recall-accent bg-recall-accent/10 px-4 py-2 text-xs font-semibold text-recall-accent hover:bg-recall-accent/20 transition"
            >
              ▶ 재개
            </button>
          )}
          {recording.status !== "ended" && (
            <button
              onClick={onStop}
              className="rounded-full bg-red-600 px-5 py-2 text-xs font-semibold text-white hover:bg-red-500 transition shadow-md active:scale-95"
            >
              ■ 회의 종료
            </button>
          )}
        </div>
      </div>

      {recording.status !== "ended" ? (
        <div className="flex-1 overflow-y-auto rounded-2xl border border-recall-border bg-white/5 p-5 shadow-inner custom-scrollbar">
          <div className="mb-3 flex items-center justify-between pb-2 border-b border-recall-border/40">
            <p className="text-xs font-bold text-recall-accent uppercase tracking-wider">
              {recording.status === "paused" ? "💬 실시간 자막 (일시정지됨)" : "💬 실시간 자막 (STT)"}
            </p>
          </div>
          {lines.length === 0 ? (
            <div className="flex h-40 items-center justify-center">
              <p className="text-sm text-recall-textMuted animate-pulse">음성을 인식하는 중입니다...</p>
            </div>
          ) : (
            <div className="space-y-3">
              {lines.map((line, i) => (
                <div key={i} className="rounded-xl bg-white/5 border border-recall-border/30 p-3">
                  <span className="text-xs font-bold text-recall-accent">{line.author}</span>
                  <p className="text-sm text-recall-text mt-1 leading-relaxed">{line.text}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="mb-4 flex gap-2 border-b border-recall-border">
            {SUMMARY_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setSummaryTab(tab.id)}
                className={`px-4 py-2 text-sm font-semibold transition ${
                  summaryTab === tab.id
                    ? "border-b-2 border-recall-accent text-recall-accent"
                    : "text-recall-textMuted hover:text-recall-text"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto rounded-2xl border border-recall-border bg-white/5 p-5 custom-scrollbar">
            {summaryTab === "script" && (
              <div className="space-y-3">
                {FAKE_STT_LINES.map((line, i) => (
                  <div key={i} className="rounded-xl bg-white/5 border border-recall-border/30 p-3">
                    <span className="text-xs font-bold text-recall-accent">{line.author}</span>
                    <p className="text-sm text-recall-text mt-1 leading-relaxed">{line.text}</p>
                  </div>
                ))}
              </div>
            )}
            {summaryTab === "summary" && (
              <div className="space-y-5">
                <div className="p-4 rounded-xl bg-recall-accent/10 border border-recall-accent/20">
                  <p className="text-xs font-bold uppercase text-recall-accent mb-1">한 줄 요약</p>
                  <p className="text-base font-bold text-recall-text">{recording.oneLineSummary}</p>
                </div>

                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-wider text-recall-textMuted">
                    전체 요약
                  </p>
                  <p className="text-sm leading-relaxed text-recall-text p-4 rounded-xl bg-white/5 border border-recall-border/40">
                    {recording.summary}
                  </p>
                </div>

                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-wider text-recall-textMuted">
                    핵심 키워드
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {recording.keywords?.map((kw) => (
                      <span
                        key={kw}
                        className="rounded-full bg-recall-accent/15 border border-recall-accent/30 px-3 py-1 text-xs font-semibold text-recall-accent"
                      >
                        #{kw}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-wider text-recall-textMuted">
                    액션 아이템
                  </p>
                  <ul className="space-y-2">
                    {recording.actionItems?.map((item, i) => (
                      <li key={i} className="flex items-center gap-2 text-sm text-recall-text p-2.5 rounded-lg bg-white/5 border border-recall-border/30">
                        <span className="text-recall-accent font-bold">✓</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function VoiceHub({
  categoryName,
  recordings,
  activeRecordingId,
  onStartNew,
  onPause,
  onResume,
  onStop,
  onSelect,
  onRename,
}: VoiceHubProps) {
  const activeRecording = recordings.find((r) => r.id === activeRecordingId) ?? null;

  return (
    <div className="flex h-full w-full bg-recall-bgMain text-recall-text">
      <div className="flex h-full flex-1 flex-col">
        {/* 🌟 상단 헤더: 버튼 사이즈를 확실하게 키우고 시선을 집중시킴 */}
        <div className="flex items-center justify-between border-b border-recall-border px-6 py-4 bg-recall-bgSoft/60">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">🎙️</span>
            <p className="truncate text-lg font-bold text-recall-text">{categoryName} 음성 회의</p>
          </div>

          {/* 💡 확실하게 커진 대형 '새 회의 시작' 버튼 */}
          <button
            onClick={onStartNew}
            className="flex items-center gap-2 rounded-xl bg-recall-accent px-6 py-3 text-sm font-bold text-white hover:opacity-95 active:scale-[0.98] transition-all shadow-md shadow-recall-accent/25"
          >
            <span className="text-base">+</span>
            <span>새 회의 시작</span>
          </button>
        </div>

        {activeRecording ? (
          <RecordingDetail
            recording={activeRecording}
            onPause={() => onPause(activeRecording.id)}
            onResume={() => onResume(activeRecording.id)}
            onStop={() => onStop(activeRecording.id)}
          />
        ) : (
          /* 선택된 회의가 없을 때 보여주는 대형 바로 시작 안내 카드 */
          <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
            <div className="flex flex-col items-center gap-4 max-w-sm p-8 rounded-2xl border border-recall-accent/30 bg-gradient-to-b from-recall-accent/15 via-recall-accent/5 to-transparent shadow-lg">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-recall-accent text-white font-bold text-3xl shadow-md shadow-recall-accent/30">
                🎙️
              </div>
              <div>
                <h3 className="text-lg font-bold text-recall-text">지금 바로 회의를 시작해 보세요</h3>
                <p className="text-xs text-recall-textMuted mt-1 leading-relaxed">
                  음성 대화가 실시간 자막으로 기록되고 AI 요약이 자동으로 생성됩니다.
                </p>
              </div>
              <button
                onClick={onStartNew}
                className="mt-2 w-full rounded-xl bg-recall-accent py-3 px-6 text-sm font-bold text-white hover:opacity-90 active:scale-95 transition shadow-md shadow-recall-accent/20"
              >
                + 새 회의 시작하기
              </button>
            </div>
          </div>
        )}
      </div>

      <RecordingListPanel
        recordings={recordings}
        activeRecordingId={activeRecordingId}
        onSelect={onSelect}
        onRename={onRename}
      />
    </div>
  );
}