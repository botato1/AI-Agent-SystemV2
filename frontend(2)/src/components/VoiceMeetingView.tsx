import { useEffect, useState } from "react";
import { VoiceMeeting, getElapsedMs } from "../hooks/useVoiceMeetings";
import { FAKE_STT_LINES, STT_LINE_INTERVAL_SECONDS } from "../data/fakeMeetingData";
import { MicIcon, PencilIcon, PlayIcon, PauseIcon, StopIcon } from "./icons";

interface VoiceMeetingViewProps {
  meetings: VoiceMeeting[];
  activeMeetingId: string | null;
  startNewMeeting: () => void;
  pauseMeeting: (id: string) => void;
  resumeMeeting: (id: string) => void;
  stopMeeting: (id: string) => void;
  renameMeeting: (id: string, name: string) => void;
  selectMeeting: (id: string | null) => void;
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const ss = String(totalSeconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function formatDate(ts: number): string {
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function statusLabel(status: VoiceMeeting["status"]): string {
  if (status === "recording") return "녹음 중";
  if (status === "paused") return "일시정지";
  if (status === "analyzing") return "분석 중";
  return "종료됨";
}

// 왼쪽 파일 목록 - 진행 중/일시정지/종료된 회의 전부, 클릭해서 전환, 이름 변경 가능
function MeetingList({
  meetings,
  activeMeetingId,
  onSelect,
  onRename,
}: {
  meetings: VoiceMeeting[];
  activeMeetingId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
}) {
  const [, setTick] = useState(0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");

  useEffect(() => {
    const hasLive = meetings.some((m) => m.status !== "ended");
    if (!hasLive) return;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [meetings]);

  function commitRename(id: string) {
    setEditingId(null);
    if (draftName.trim()) onRename(id, draftName.trim());
  }

  return (
    <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
        음성 파일 목록
      </p>
      <div className="flex-1 space-y-1.5 overflow-y-auto">
        {meetings.length === 0 ? (
          <p className="text-xs text-recall-textMuted">아직 녹음이 없어요.</p>
        ) : (
          meetings.map((m) => {
            const isSelected = m.id === activeMeetingId;
            return (
              <div
                key={m.id}
                onClick={() => onSelect(m.id)}
                className={`group flex cursor-pointer flex-col gap-0.5 rounded-lg border px-2.5 py-2 ${
                  isSelected
                    ? "border-recall-accent bg-recall-accent/10"
                    : "border-recall-border hover:bg-white/5"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  {m.status === "recording" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-danger" />
                  )}
                  {m.status === "paused" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-textMuted" />
                  )}
                  {m.status === "analyzing" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 animate-pulse rounded-full bg-recall-accent" />
                  )}
                  {editingId === m.id ? (
                    <input
                      autoFocus
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onBlur={() => commitRename(m.id)}
                      onKeyDown={(e) => e.key === "Enter" && commitRename(m.id)}
                      className="min-w-0 flex-1 rounded border border-recall-border bg-transparent px-1 text-xs text-recall-text focus:outline-none focus:border-recall-accent"
                    />
                  ) : (
                    <span className="truncate text-xs font-medium text-recall-text">{m.name}</span>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingId(m.id);
                      setDraftName(m.name);
                    }}
                    className="ml-auto hidden flex-shrink-0 text-recall-textMuted hover:text-recall-text group-hover:inline"
                    aria-label="이름 변경"
                  >
                    <PencilIcon size={12} />
                  </button>
                </div>
                <span className="text-[11px] text-recall-textMuted">
                  {statusLabel(m.status)} · {formatDate(m.createdAt)} · {formatDuration(getElapsedMs(m))}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

type ResultTab = "script" | "summary";

// 오른쪽 상세 영역 - 진행 중이면 실시간 STT + 컨트롤, 종료되면 분석 결과(발화시간/발화자별/스크립트/요약)
function MeetingDetail({
  meeting,
  onPause,
  onResume,
  onStop,
}: {
  meeting: VoiceMeeting;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}) {
  const [, setTick] = useState(0);
  const [resultTab, setResultTab] = useState<ResultTab>("script");

  useEffect(() => {
    if (meeting.status !== "recording") return;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [meeting.status]);

  const elapsedMs = getElapsedMs(meeting);
  const elapsedSeconds = elapsedMs / 1000;
  const revealedCount = Math.min(
    FAKE_STT_LINES.length,
    Math.floor(elapsedSeconds / STT_LINE_INTERVAL_SECONDS)
  );
  const liveLines = FAKE_STT_LINES.slice(0, revealedCount);

  return (
    <div className="flex h-full flex-1 flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-recall-text">{meeting.name}</p>
          <p className="text-xs text-recall-textMuted">
            {statusLabel(meeting.status)} · {formatDuration(elapsedMs)}
          </p>
        </div>
        <div className="flex gap-1.5">
          {meeting.status === "recording" && (
            <button
              onClick={onPause}
              className="flex items-center gap-1.5 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              <PauseIcon size={13} />
              일시정지
            </button>
          )}
          {meeting.status === "paused" && (
            <button
              onClick={onResume}
              className="flex items-center gap-1.5 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              <PlayIcon size={13} />
              재개
            </button>
          )}
          {(meeting.status === "recording" || meeting.status === "paused") && (
            <button
              onClick={onStop}
              className="flex items-center gap-1.5 rounded-lg border border-recall-danger px-2.5 py-1.5 text-xs font-medium text-recall-danger"
            >
              <StopIcon size={13} />
              종료
            </button>
          )}
        </div>
      </div>

      {meeting.status === "analyzing" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-recall-border">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
          <p className="text-sm text-recall-textMuted">
            발화자 분리, 스크립트 정리, 요약을 만드는 중이에요...
          </p>
        </div>
      ) : meeting.status !== "ended" ? (
        <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
          <p className="mb-2 text-xs text-recall-textMuted">
            {meeting.status === "paused" ? "실시간 STT (일시정지됨)" : "실시간 STT"}
          </p>
          {liveLines.length === 0 ? (
            <p className="text-sm text-recall-textMuted">듣는 중...</p>
          ) : (
            <div className="space-y-2 text-sm text-recall-textMuted">
              {liveLines.map((line, i) => (
                <p key={i}>
                  <span className="font-medium text-recall-text">{line.author}</span> {line.text}
                </p>
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          {/* 총 발화 시간 + 발화자별 발화 길이 */}
          <div className="mb-3 rounded-lg border border-recall-border p-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
              총 발화 시간 · {formatDuration(elapsedMs)}
            </p>
            <div className="space-y-1.5">
              {meeting.speakerStats?.map((s) => {
                const pct = elapsedMs > 0 ? Math.round((s.ms / elapsedMs) * 100) : 0;
                return (
                  <div key={s.name} className="flex items-center gap-2">
                    <span className="w-10 flex-shrink-0 text-xs text-recall-text">{s.name}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-recall-border">
                      <div className="h-full rounded-full bg-recall-accent" style={{ width: `${pct}%` }} />
                    </div>
                    <span className="w-16 flex-shrink-0 text-right text-xs text-recall-textMuted">
                      {formatDuration(s.ms)} ({pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="mb-3 flex gap-0.5 border-b border-recall-border">
            <button
              onClick={() => setResultTab("script")}
              className={`px-2 py-1 text-xs ${
                resultTab === "script"
                  ? "border-b-2 border-recall-accent text-recall-text"
                  : "text-recall-textMuted hover:text-recall-text"
              }`}
            >
              전체 스크립트
            </button>
            <button
              onClick={() => setResultTab("summary")}
              className={`px-2 py-1 text-xs ${
                resultTab === "summary"
                  ? "border-b-2 border-recall-accent text-recall-text"
                  : "text-recall-textMuted hover:text-recall-text"
              }`}
            >
              요약
            </button>
          </div>

          <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
            {resultTab === "script" ? (
              <div className="space-y-2 text-sm text-recall-textMuted">
                {FAKE_STT_LINES.map((line, i) => (
                  <p key={i}>
                    <span className="font-medium text-recall-text">{line.author}</span> {line.text}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-sm text-recall-text">{meeting.summary}</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function VoiceMeetingView({
  meetings,
  activeMeetingId,
  startNewMeeting,
  pauseMeeting,
  resumeMeeting,
  stopMeeting,
  renameMeeting,
  selectMeeting,
}: VoiceMeetingViewProps) {
  const activeMeeting = meetings.find((m) => m.id === activeMeetingId) ?? null;
  // 이미 진행 중인 녹음(녹음중/일시정지/분석중)이 있으면 새 녹음을 못 시작하게 막음
  // - 여러 명이 동시에 다른 녹음을 시작해버리는 걸 방지하기 위함
  const ongoingMeeting = meetings.find((m) => m.status !== "ended") ?? null;

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
      <div className="flex items-center justify-between border-b border-recall-border p-3">
        <p className="text-sm font-medium">음성 회의</p>
        <button
          onClick={startNewMeeting}
          disabled={!!ongoingMeeting}
          title={ongoingMeeting ? `"${ongoingMeeting.name}"이(가) 진행 중이에요` : undefined}
          className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs ${
            ongoingMeeting
              ? "cursor-not-allowed border-recall-border text-recall-textMuted opacity-50"
              : "border-recall-border text-recall-text hover:bg-white/5"
          }`}
        >
          <MicIcon size={14} />
          새 녹음 시작
        </button>
      </div>

      {ongoingMeeting && (
        <div className="flex items-center gap-1.5 border-b border-recall-border bg-recall-danger/10 px-3 py-2 text-xs text-recall-danger">
          <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-danger" />
          "{ongoingMeeting.name}" 녹음이 진행 중이라 새 녹음은 시작할 수 없어요. 먼저 종료해주세요.
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <MeetingList
          meetings={meetings}
          activeMeetingId={activeMeetingId}
          onSelect={selectMeeting}
          onRename={renameMeeting}
        />

        {activeMeeting ? (
          <MeetingDetail
            meeting={activeMeeting}
            onPause={() => pauseMeeting(activeMeeting.id)}
            onResume={() => resumeMeeting(activeMeeting.id)}
            onStop={() => stopMeeting(activeMeeting.id)}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-recall-textMuted">
              "새 녹음 시작"을 누르거나 왼쪽 목록에서 파일을 선택하세요.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}