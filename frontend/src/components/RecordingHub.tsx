import { useEffect, useState } from "react";
import {
  RecordingSession,
  getElapsedMs,
  useRecordingSessions,
} from "../hooks/useRecordingSessions";
import { FAKE_STT_LINES, STT_LINE_INTERVAL_SECONDS } from "../data/fakeMeetingData";

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const ss = String(totalSeconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function statusLabel(status: RecordingSession["status"]): string {
  if (status === "recording") return "녹음 중";
  if (status === "paused") return "일시정지";
  return "종료됨";
}

function RecordingList({
  sessions,
  activeSessionId,
  onSelect,
}: {
  sessions: RecordingSession[];
  activeSessionId: string | null;
  onSelect: (id: string) => void;
}) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const hasLiveSession = sessions.some((s) => s.status !== "ended");
    if (!hasLiveSession) return;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [sessions]);

  return (
    <div className="flex h-full w-56 flex-shrink-0 flex-col border-l border-recall-border bg-recall-bgSoft p-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
        녹음 목록
      </p>
      <div className="flex-1 space-y-1.5 overflow-y-auto">
        {sessions.length === 0 ? (
          <p className="text-xs text-recall-textMuted">아직 녹음이 없어요.</p>
        ) : (
          sessions.map((s) => {
            const isSelected = s.id === activeSessionId;
            return (
              <button
                key={s.id}
                onClick={() => onSelect(s.id)}
                className={`flex w-full flex-col gap-0.5 rounded-lg border px-2.5 py-2 text-left ${
                  isSelected
                    ? "border-recall-accent bg-recall-accent/10"
                    : "border-recall-border hover:bg-white/5"
                }`}
              >
                <span className="flex items-center gap-1.5 text-xs font-medium text-recall-text">
                  {s.status === "recording" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-danger" />
                  )}
                  {s.status === "paused" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-textMuted" />
                  )}
                  <span className="truncate">{s.name}</span>
                </span>
                <span className="text-[11px] text-recall-textMuted">
                  {statusLabel(s.status)} · {formatDuration(getElapsedMs(s))}
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function RecordingDetail({
  session,
  onPause,
  onResume,
  onStop,
}: {
  session: RecordingSession;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}) {
  const [, setTick] = useState(0);

  useEffect(() => {
    if (session.status !== "recording") return;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [session.status]);

  const elapsedMs = getElapsedMs(session);
  const elapsedSeconds = elapsedMs / 1000;
  const revealedCount = Math.min(
    FAKE_STT_LINES.length,
    Math.floor(elapsedSeconds / STT_LINE_INTERVAL_SECONDS)
  );
  const lines = FAKE_STT_LINES.slice(0, revealedCount);

  return (
    <div className="flex h-full flex-1 flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-recall-text">{session.name}</p>
          <p className="text-xs text-recall-textMuted">
            {statusLabel(session.status)} · {formatDuration(elapsedMs)}
          </p>
        </div>
        <div className="flex gap-1.5">
          {session.status === "recording" && (
            <button
              onClick={onPause}
              className="rounded border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              ❚❚ 일시정지
            </button>
          )}
          {session.status === "paused" && (
            <button
              onClick={onResume}
              className="rounded border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              ▶ 재개
            </button>
          )}
          {session.status !== "ended" && (
            <button
              onClick={onStop}
              className="rounded border border-recall-danger px-2.5 py-1.5 text-xs font-medium text-recall-danger"
            >
              ■ 종료
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
        <p className="mb-2 text-xs text-recall-textMuted">
          {session.status === "paused" ? "실시간 STT (일시정지됨)" : "실시간 STT"}
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

      {session.status === "ended" && session.summary && (
        <div className="mt-3 rounded-lg border border-recall-border p-3">
          <p className="mb-1 text-xs text-recall-textMuted">요약</p>
          <p className="text-sm text-recall-text">{session.summary}</p>
        </div>
      )}
    </div>
  );
}

export default function RecordingHub() {
  const {
    sessions,
    activeSessionId,
    setActiveSessionId,
    startNewRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
  } = useRecordingSessions();

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null;

  return (
    <div className="flex h-full w-full bg-recall-bgMain text-recall-text">
      <div className="flex h-full flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-recall-border p-3">
          <p className="text-sm font-medium">🎙 음성</p>
          <button
            onClick={startNewRecording}
            className="rounded border border-recall-border px-3 py-1.5 text-xs text-recall-text hover:bg-white/5"
          >
            🎤 새 녹음 시작
          </button>
        </div>

        {activeSession ? (
          <RecordingDetail
            session={activeSession}
            onPause={() => pauseRecording(activeSession.id)}
            onResume={() => resumeRecording(activeSession.id)}
            onStop={() => stopRecording(activeSession.id)}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-recall-textMuted">
              "새 녹음 시작"을 누르거나 오른쪽 목록에서 녹음을 선택하세요.
            </p>
          </div>
        )}
      </div>

      <RecordingList
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelect={setActiveSessionId}
      />
    </div>
  );
}