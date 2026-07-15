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

// 오른쪽 녹음 목록 - 지금까지 만든 녹음 전부, 클릭하면 왼쪽 메인 화면에서 보여줌
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
    <div className="flex h-full w-56 flex-shrink-0 flex-col border-l border-recall-border bg-recall-bgSoft p-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
        녹음 목록
      </p>
      <div className="flex-1 space-y-1.5 overflow-y-auto">
        {recordings.length === 0 ? (
          <p className="text-xs text-recall-textMuted">아직 녹음이 없어요.</p>
        ) : (
          recordings.map((r) => {
            const isSelected = r.id === activeRecordingId;
            return (
              <div
                key={r.id}
                onClick={() => onSelect(r.id)}
                className={`group flex cursor-pointer flex-col gap-0.5 rounded-lg border px-2.5 py-2 ${
                  isSelected
                    ? "border-recall-accent bg-recall-accent/10"
                    : "border-recall-border hover:bg-white/5"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  {r.status === "recording" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-danger" />
                  )}
                  {r.status === "paused" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-textMuted" />
                  )}
                  {editingId === r.id ? (
                    <input
                      autoFocus
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onBlur={() => commitRename(r.id)}
                      onKeyDown={(e) => e.key === "Enter" && commitRename(r.id)}
                      className="min-w-0 flex-1 rounded border border-recall-border bg-transparent px-1 text-xs text-recall-text focus:outline-none focus:border-recall-accent"
                    />
                  ) : (
                    <span className="truncate text-xs font-medium text-recall-text">{r.name}</span>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingId(r.id);
                      setDraftName(r.name);
                    }}
                    className="ml-auto hidden flex-shrink-0 text-recall-textMuted hover:text-recall-text group-hover:inline"
                    aria-label="이름 변경"
                  >
                    ✎
                  </button>
                </div>
                <span className="text-[11px] text-recall-textMuted">
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

// 왼쪽 메인 영역 - 선택된 녹음의 실시간(진행 중) STT 또는 종료 후 탭별 결과
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
  // 일시정지 중엔 시간이 안 흐르니 자막도 그 시점에서 멈춰있고, 재개하면 이어서 늘어남
  const revealedCount = Math.min(
    FAKE_STT_LINES.length,
    Math.floor(elapsedSeconds / STT_LINE_INTERVAL_SECONDS)
  );
  const lines = FAKE_STT_LINES.slice(0, revealedCount);

  return (
    <div className="flex h-full flex-1 flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-recall-text">{recording.name}</p>
          <p className="text-xs text-recall-textMuted">
            {statusLabel(recording.status)} · {formatDuration(elapsedMs)}
          </p>
        </div>
        <div className="flex gap-1.5">
          {recording.status === "recording" && (
            <button
              onClick={onPause}
              className="rounded border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              ❚❚ 일시정지
            </button>
          )}
          {recording.status === "paused" && (
            <button
              onClick={onResume}
              className="rounded border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              ▶ 재개
            </button>
          )}
          {recording.status !== "ended" && (
            <button
              onClick={onStop}
              className="rounded border border-recall-danger px-2.5 py-1.5 text-xs font-medium text-recall-danger"
            >
              ■ 종료
            </button>
          )}
        </div>
      </div>

      {recording.status !== "ended" ? (
        <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
          <p className="mb-2 text-xs text-recall-textMuted">
            {recording.status === "paused" ? "실시간 STT (일시정지됨)" : "실시간 STT"}
          </p>
          {lines.length === 0 ? (
            <p className="text-sm text-recall-textMuted">듣는 중...</p>
          ) : (
            <div className="space-y-2 text-sm text-recall-textMuted">
              {lines.map((line, i) => (
                <p key={i}>
                  <span className="font-medium text-recall-text">{line.author}</span> {line.text}
                </p>
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="mb-3 flex gap-0.5 border-b border-recall-border">
            {SUMMARY_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setSummaryTab(tab.id)}
                className={`px-2 py-1 text-xs ${
                  summaryTab === tab.id
                    ? "border-b-2 border-recall-accent text-recall-text"
                    : "text-recall-textMuted hover:text-recall-text"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
            {summaryTab === "script" && (
              <div className="space-y-2 text-sm text-recall-textMuted">
                {FAKE_STT_LINES.map((line, i) => (
                  <p key={i}>
                    <span className="font-medium text-recall-text">{line.author}</span> {line.text}
                  </p>
                ))}
              </div>
            )}
            {summaryTab === "summary" && (
              <div className="space-y-4">
                <div>
                  <p className="text-sm font-medium text-recall-text">{recording.oneLineSummary}</p>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
                    전체요약
                  </p>
                  <p className="text-sm text-recall-text">{recording.summary}</p>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
                    키워드
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {recording.keywords?.map((kw) => (
                      <span
                        key={kw}
                        className="rounded-full border border-recall-border px-2.5 py-1 text-xs text-recall-text"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
                    액션 아이템
                  </p>
                  <ul className="space-y-1">
                    {recording.actionItems?.map((item, i) => (
                      <li key={i} className="text-sm text-recall-text">
                        · {item}
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
        <div className="flex items-center justify-between border-b border-recall-border p-3">
          <p className="truncate text-sm font-medium">🎙 {categoryName} 음성</p>
          <button
            onClick={onStartNew}
            className="rounded border border-recall-border px-3 py-1.5 text-xs text-recall-text hover:bg-white/5"
          >
            🎤 새 녹음 시작
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
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-recall-textMuted">
              "새 녹음 시작"을 누르거나 오른쪽 목록에서 녹음을 선택하세요.
            </p>
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