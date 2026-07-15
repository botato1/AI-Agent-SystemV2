import { useEffect, useState } from "react";
import { VoiceMeeting, getElapsedMs } from "../hooks/useVoiceMeetings";
import { STT_LINE_INTERVAL_SECONDS } from "../data/fakeMeetingData";
import { MicIcon, PencilIcon, PlayIcon, PauseIcon, StopIcon } from "./icons";

// ResultTab 타입 정의
type ResultTab = "script" | "summary";

interface VoiceMeetingViewProps {
  meetings: VoiceMeeting[];
  activeMeetingId: string | null;
  startNewMeeting: () => void;
  pauseMeeting: (id: string) => void;
  resumeMeeting: (id: string) => void;
  stopMeeting: (id: string) => void;
  renameMeeting: (id: string, name: string) => void;
  selectMeeting: (id: string | null) => void;
  t: any;
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

// 왼쪽 파일 목록
function MeetingList({
  meetings,
  activeMeetingId,
  onSelect,
  onRename,
  t,
}: {
  meetings: VoiceMeeting[];
  activeMeetingId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
  t: any;
}) {
  const [, setTick] = useState(0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");

  useEffect(() => {
    const hasLive = meetings.some((m) => m.status !== "ended");
    if (!hasLive) return;
    const timer = setInterval(() => setTick((tk) => tk + 1), 1000);
    return () => clearInterval(timer);
  }, [meetings]);

  function statusLabel(status: VoiceMeeting["status"]) {
    if (status === "recording") return t.voice_status_recording;
    if (status === "paused") return t.voice_status_paused;
    if (status === "analyzing") return t.voice_status_analyzing;
    return t.voice_status_ended;
  }

  function commitRename(id: string) {
    setEditingId(null);
    if (draftName.trim()) onRename(id, draftName.trim());
  }

  return (
    <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
        {t.voice_meeting_list_title}
      </p>
      <div className="flex-1 space-y-1.5 overflow-y-auto">
        {meetings.length === 0 ? (
          <p className="text-xs text-recall-textMuted">{t.dashboard_no_contradiction}</p>
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
                    aria-label="Rename"
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

// 오른쪽 상세 영역 (Props 인터페이스에 lang 추가)
function MeetingDetail({
  meeting,
  onPause,
  onResume,
  onStop,
  t,
  lang, // 부모로부터 받은 lang 명시
}: {
  meeting: VoiceMeeting;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  t: any;
  lang: string; // 타입 명시
}) {
  const [, setTick] = useState(0);
  const [resultTab, setResultTab] = useState<ResultTab>("script");

  useEffect(() => {
    if (meeting.status !== "recording") return;
    const timer = setInterval(() => setTick((tk) => tk + 1), 1000);
    return () => clearInterval(timer);
  }, [meeting.status]);

  const STT_TRANSLATIONS = [
    { author: t.name_jisu, text: t.stt_line_1 },
    { author: t.name_donghyun, text: t.stt_line_2 },
    { author: t.name_nayeon, text: t.stt_line_3 },
    { author: t.name_jisu, text: t.stt_line_4 },
  ];

  const elapsedMs = getElapsedMs(meeting);
  const elapsedSeconds = elapsedMs / 1000;
  const revealedCount = Math.min(
    STT_TRANSLATIONS.length,
    Math.floor(elapsedSeconds / STT_LINE_INTERVAL_SECONDS)
  );
  const liveLines = STT_TRANSLATIONS.slice(0, revealedCount);

  function statusLabel(status: VoiceMeeting["status"]) {
    if (status === "recording") return t.voice_status_recording;
    if (status === "paused") return t.voice_status_paused;
    if (status === "analyzing") return t.voice_status_analyzing;
    return t.voice_status_ended;
  }

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
              {lang === "ko" ? "일시정지" : "Pause"}
            </button>
          )}
          {meeting.status === "paused" && (
            <button
              onClick={onResume}
              className="flex items-center gap-1.5 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
            >
              <PlayIcon size={13} />
              {lang === "ko" ? "재개" : "Resume"}
            </button>
          )}
          {(meeting.status === "recording" || meeting.status === "paused") && (
            <button
              onClick={onStop}
              className="flex items-center gap-1.5 rounded-lg border border-recall-danger px-2.5 py-1.5 text-xs font-medium text-recall-danger"
            >
              <StopIcon size={13} />
              {lang === "ko" ? "종료" : "Stop"}
            </button>
          )}
        </div>
      </div>

      {meeting.status === "analyzing" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-recall-border">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
          <p className="text-sm text-recall-textMuted">{t.stt_analyzing}</p>
        </div>
      ) : meeting.status !== "ended" ? (
        <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
          <p className="mb-2 text-xs text-recall-textMuted">
            {meeting.status === "paused" ? t.realtime_stt_paused : t.realtime_stt}
          </p>
          {liveLines.length === 0 ? (
            <p className="text-sm text-recall-textMuted">{t.stt_listening}</p>
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
          <div className="mb-3 rounded-lg border border-recall-border p-3">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
              {t.speaker_stats_title} · {formatDuration(elapsedMs)}
            </p>
            <div className="space-y-1.5">
              {meeting.speakerStats?.map((s) => {
                const pct = elapsedMs > 0 ? Math.round((s.ms / elapsedMs) * 100) : 0;
                const translatedSpeaker = s.name === "지수" ? t.name_jisu : s.name === "나연" ? t.name_nayeon : s.name === "승주" ? t.name_seungju : t.name_donghyun;
                return (
                  <div key={s.name} className="flex items-center gap-2">
                    <span className="w-16 flex-shrink-0 text-xs text-recall-text">{translatedSpeaker}</span>
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
              {t.tab_script}
            </button>
            <button
              onClick={() => setResultTab("summary")}
              className={`px-2 py-1 text-xs ${
                resultTab === "summary"
                  ? "border-b-2 border-recall-accent text-recall-text"
                  : "text-recall-textMuted hover:text-recall-text"
              }`}
            >
              {t.tab_summary}
            </button>
          </div>

          <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
            {resultTab === "script" ? (
              <div className="space-y-2 text-sm text-recall-textMuted">
                {STT_TRANSLATIONS.map((line, i) => (
                  <p key={i}>
                    <span className="font-medium text-recall-text">{line.author}</span> {line.text}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-sm text-recall-text">
                {lang === "ko" ? meeting.summary : "Discussed API Gateway unification plan, raised concerns on tax dashboard integration conflict. Decided to review in detail by the next meeting."}
              </p>
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
  t,
}: VoiceMeetingViewProps) {
  const activeMeeting = meetings.find((m) => m.id === activeMeetingId) ?? null;
  const ongoingMeeting = meetings.find((m) => m.status !== "ended") ?? null;

  // 번역 사전의 특정 키를 기준으로 현재의 언어(lang) 판별
  const lang = t.settings_lang === "언어" ? "ko" : "en";

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
      <div className="flex items-center justify-between border-b border-recall-border p-3">
        <p className="text-sm font-medium">{t.sidebar_voice_meeting}</p>
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
          {t.voice_btn_start}
        </button>
      </div>

      {ongoingMeeting && (
        <div className="flex items-center gap-1.5 border-b border-recall-border bg-recall-danger/10 px-3 py-2 text-xs text-recall-danger">
          <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-danger" />
          {t.voice_meeting_running_alert}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <MeetingList
          meetings={meetings}
          activeMeetingId={activeMeetingId}
          onSelect={selectMeeting}
          onRename={renameMeeting}
          t={t}
        />

        {activeMeeting ? (
          <MeetingDetail
            meeting={activeMeeting}
            onPause={() => pauseMeeting(activeMeeting.id)}
            onResume={() => resumeMeeting(activeMeeting.id)}
            onStop={() => stopMeeting(activeMeeting.id)}
            t={t}
            lang={lang} // 자식에게 판별된 lang 전달 (오류 완치)
          />
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-recall-textMuted">{t.meeting_not_started}</p>
          </div>
        )}
      </div>
    </div>
  );
}