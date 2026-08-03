import { useEffect, useRef, useState } from "react";
import { useRealMeetings } from "../hooks/useRealMeetings";
import { LiveMeetingStatus, LiveSegment, ContradictionAlert } from "../hooks/useLiveMeeting";
import { useContradictions } from "../hooks/useContradictions";
import { Meeting, MeetingStatus, MeetingAttendee, RecordingMode } from "../services/meeting";
import { ContradictionSeverity } from "../services/contradiction";
import {
  UploadIcon,
  TrashIcon,
  DocumentIcon,
  MicIcon,
  PauseIcon,
  PlayIcon,
  StopIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  WarningIcon,
  PencilIcon,
  PersonIcon,
} from "./icons";
import ContradictionMessage from "./ContradictionMessage";
import ChangeSummaryModal from "./ChangeSummaryModal";
import DocumentPreviewModal from "./DocumentPreviewModal";
import MeetingAttendeesModal from "./MeetingAttendeesModal";
import MeetingExportModal from "./MeetingExportModal";
import MeetingStartModal from "./MeetingStartModal";
import { hashAvatarColor } from "../data/avatarColors";

function severityBadge(severity: ContradictionSeverity, t: any) {
  const map = {
    high: { label: t.priority_high, className: "bg-recall-danger/15 text-recall-danger" },
    medium: { label: t.priority_medium, className: "bg-amber-500/15 text-amber-400" },
    low: { label: t.priority_low, className: "bg-recall-textMuted/15 text-recall-textMuted" },
  } as const;
  const { label, className } = map[severity];
  return <span className={`flex-shrink-0 rounded-full px-1.5 py-0.5 text-[11px] ${className}`}>{label}</span>;
}

type DetailTab = "summary" | "minutes" | "script";

const ACCEPTED_EXTENSIONS = ".mp3,.wav,.m4a,.webm";
const LIVE_ACTIVE_STATUSES: LiveMeetingStatus[] = [
  "connecting",
  "recording",
  "paused",
  "reconnecting",
  "ending",
];

function formatDate(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

function formatDuration(ms?: number | null): string {
  if (!ms) return "-";
  const totalSeconds = Math.floor(ms / 1000);
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const ss = String(totalSeconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function formatDateOnly(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

function formatTimeOnly(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function groupAttendees(attendees: MeetingAttendee[]) {
  return {
    initial: attendees.filter((a) => a.is_initial !== false),
    added: attendees.filter((a) => a.is_initial === false),
  };
}

function isRawSpeakerLabel(label: string | null | undefined): label is string {
  return !!label && /^SPEAKER[_\s]?\d+$/i.test(label.trim());
}

function SegmentRow({
  speakerLabel,
  timeMs,
  content,
  hasContradiction,
  t,
}: {
  speakerLabel: string | null | undefined;
  timeMs: number;
  content: string;
  hasContradiction?: boolean;
  t: any;
}) {
  const name = speakerLabel || t.speaker_unknown;
  const isIdentified = !isRawSpeakerLabel(speakerLabel);
  return (
    <div className={`flex gap-2 rounded-lg ${hasContradiction ? "-mx-1.5 border border-recall-danger/30 bg-recall-danger/5 px-1.5 py-1" : ""}`}>
      <div
        className={`mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white ${
          isIdentified ? "" : "bg-recall-border text-recall-textMuted"
        }`}
        style={isIdentified ? { backgroundColor: hashAvatarColor(name) } : undefined}
      >
        {isIdentified ? name.trim().charAt(0).toUpperCase() : <PersonIcon size={13} />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-1.5">
          <span className={`font-medium ${isIdentified ? "text-recall-text" : "text-recall-textMuted"}`}>
            {name}
          </span>
          <span className="text-xs text-recall-textMuted/70">{formatDuration(timeMs)}</span>
          {hasContradiction && (
            <WarningIcon size={12} className="flex-shrink-0 text-recall-danger" />
          )}
        </p>
        <p className="text-recall-textMuted">{content}</p>
      </div>
    </div>
  );
}

function uniqueRawSpeakerLabels(labels: (string | null | undefined)[]): string[] {
  const seen = new Set<string>();
  for (const l of labels) {
    if (isRawSpeakerLabel(l)) seen.add(l.trim());
  }
  return Array.from(seen);
}

function statusBadge(status: MeetingStatus) {
  switch (status) {
    case "created":
    case "processing":
      return { label: "분석 중", className: "bg-recall-accent/10 text-recall-accent" };
    case "completed":
      return { label: "완료", className: "bg-emerald-500/10 text-emerald-400" };
    case "failed":
      return { label: "실패", className: "bg-recall-danger/10 text-recall-danger" };
    case "recording":
      return { label: "녹음 중", className: "bg-recall-danger/10 text-recall-danger" };
    case "paused":
      return { label: "일시정지", className: "bg-recall-textMuted/10 text-recall-textMuted" };
    default:
      return { label: status, className: "bg-recall-textMuted/10 text-recall-textMuted" };
  }
}

function liveStatusLabel(status: LiveMeetingStatus): string {
  switch (status) {
    case "connecting":
      return "연결 중...";
    case "recording":
      return "녹음 중";
    case "paused":
      return "일시정지";
    case "reconnecting":
      return "재연결 중...";
    case "ending":
      return "종료 처리 중...";
    default:
      return "";
  }
}

function UploadModal({
  isUploading,
  onClose,
  onUpload,
}: {
  isUploading: boolean;
  onClose: () => void;
  onUpload: (file: File, title: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !file) return;
    onUpload(file, title.trim());
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-2xl text-recall-text">
        <h3 className="mb-4 text-lg font-bold">회의 음성 업로드</h3>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-semibold text-recall-textMuted">회의 제목</label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="예: 주간 스프린트 회의"
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-sm text-recall-text outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-semibold text-recall-textMuted">
              음성 파일 (mp3/wav/m4a/webm)
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-sm text-recall-text outline-none file:mr-2 file:rounded file:border-0 file:bg-recall-accent/15 file:px-2 file:py-1 file:text-recall-accent"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-recall-border px-3.5 py-2 text-sm text-recall-textMuted hover:bg-white/5"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isUploading || !title.trim() || !file}
              className="rounded-lg bg-recall-accent px-3.5 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
            >
              {isUploading ? "업로드 중..." : "업로드"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface MeetingsPanelProps {
  workspaceId: string;
  liveStatus: LiveMeetingStatus;
  liveMeeting: Meeting | null;
  liveSegments: LiveSegment[];
  livePartial: { confirmed: string; tentative: string };
  liveContradictionAlerts: ContradictionAlert[];
  liveError: string | null;
  joinableMeeting: Meeting | null;
  onStartLive: (
    title: string,
    relatedRoomId?: string,
    attendeeIds?: string[],
    location?: string,
    recordingMode?: RecordingMode
  ) => void;
  onJoinLive: (meetingId: string) => void;
  onPauseLive: () => void;
  onResumeLive: () => void;
  onStopLive: () => void;
  onResetLive: () => void;
  onMapLiveSpeakers: (mapping: Record<string, string>) => void;
  onRenameLive: (title: string) => void;
  t: any;
}

function EditableMeetingTitle({ title, onRename }: { title: string; onRename: (title: string) => void }) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(title);

  function commit() {
    setIsEditing(false);
    const trimmed = draft.trim();
    if (trimmed && trimmed !== title) {
      onRename(trimmed);
    }
  }

  if (isEditing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onFocus={(e) => e.target.select()}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") {
            setDraft(title);
            setIsEditing(false);
          }
        }}
        className="rounded border border-recall-border bg-transparent px-1.5 py-0.5 text-base font-medium text-recall-text focus:outline-none focus:border-recall-accent"
      />
    );
  }

  return (
    <button
      onClick={() => {
        setDraft(title);
        setIsEditing(true);
      }}
      title="제목 수정"
      className="group flex items-center gap-1.5 text-left"
    >
      <span className="text-base font-medium text-recall-text">{title}</span>
      <PencilIcon size={12} className="flex-shrink-0 text-recall-textMuted opacity-0 group-hover:opacity-70" />
    </button>
  );
}

function UnmappedSpeakerChips({
  labels,
  onAssign,
}: {
  labels: string[];
  onAssign: (mapping: Record<string, string>) => void;
}) {
  if (labels.length === 0) return null;

  function handleClick(label: string) {
    const name = window.prompt(`"${label}"의 실제 이름을 입력해 주세요.`, "");
    if (!name || !name.trim()) return;
    onAssign({ [label]: name.trim() });
  }

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-recall-textMuted">화자 이름 지정:</span>
      {labels.map((label) => (
        <button
          key={label}
          onClick={() => handleClick(label)}
          className="rounded-full border border-recall-border px-2 py-0.5 text-xs text-recall-textMuted hover:border-recall-accent hover:text-recall-accent"
        >
          {label} +
        </button>
      ))}
    </div>
  );
}

export default function MeetingsPanel({
  workspaceId,
  liveStatus,
  liveMeeting,
  liveSegments,
  livePartial,
  liveContradictionAlerts,
  liveError,
  joinableMeeting,
  onStartLive,
  onJoinLive,
  onPauseLive,
  onResumeLive,
  onStopLive,
  onResetLive,
  onMapLiveSpeakers,
  onRenameLive,
  t,
}: MeetingsPanelProps) {
  const {
    meetings: realMeetings,
    isLoading,
    selectedMeetingId,
    setSelectedMeetingId,
    selectedMeeting: selectedRealMeeting,
    segments,
    summary,
    decisions,
    attendees,
    reloadAttendees,
    isDetailLoading,
    isUploading,
    uploadAudio,
    removeMeeting,
    renameMeeting,
    mapSpeakerNames,
    reload,
  } = useRealMeetings(workspaceId);

  const {
    contradictions: workspaceContradictions,
    isLoading: isContradictionsLoading,
    statusFilter: contradictionStatusFilter,
    setStatusFilter: setContradictionStatusFilter,
    resolve,
    dismiss,
    reopen,
    refresh: refreshContradictions,
    pendingSummaryFor,
    changeSummary,
    isChangeSummaryLoading,
    closeChangeSummary,
  } = useContradictions(workspaceId);

  const prevAlertCountRef = useRef(liveContradictionAlerts.length);
  useEffect(() => {
    if (liveContradictionAlerts.length > prevAlertCountRef.current) {
      refreshContradictions();
    }
    prevAlertCountRef.current = liveContradictionAlerts.length;
  }, [liveContradictionAlerts.length]);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("summary");
  const [isMeetingListOpen, setIsMeetingListOpen] = useState(true);
  const [isContradictionListOpen, setIsContradictionListOpen] = useState(true);
  const [expandedContradictionIds, setExpandedContradictionIds] = useState<Set<string>>(new Set());
  const [previewDoc, setPreviewDoc] = useState<{ id: string; name: string } | null>(null);
  const [showAttendeesModal, setShowAttendeesModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showStartModal, setShowStartModal] = useState(false);

  function toggleContradictionExpanded(id: string) {
    setExpandedContradictionIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const isLiveActive = LIVE_ACTIVE_STATUSES.includes(liveStatus);

  const meetings: Meeting[] =
    isLiveActive && liveMeeting
      ? [liveMeeting, ...realMeetings.filter((m) => m.id !== liveMeeting.id)]
      : realMeetings;

  const isViewingLive = isLiveActive && !!liveMeeting && selectedMeetingId === liveMeeting.id;

  const contradictions = workspaceContradictions.filter((c) => {
    if (c.source_type !== "meeting_segment") return false;
    if (isViewingLive) {
      if (!liveMeeting) return false;
      const startedAt = liveMeeting.started_at || liveMeeting.created_at;
      return !startedAt || new Date(c.detected_at) >= new Date(startedAt);
    }
    if (!selectedRealMeeting) return false;
    return !!c.meeting_segment_id && segments.some((s) => s.id === c.meeting_segment_id);
  });

  const prevContradictionCountRef = useRef(contradictions.length);

  useEffect(() => {
    if (contradictions.length > prevContradictionCountRef.current) {
      setIsContradictionListOpen((prevOpen) => (prevOpen ? prevOpen : true));
    }
    prevContradictionCountRef.current = contradictions.length;
  }, [contradictions.length]);

  useEffect(() => {
    if (isLiveActive && liveMeeting) {
      setSelectedMeetingId(liveMeeting.id);
    }
  }, [isLiveActive, liveMeeting?.id]);

  useEffect(() => {
    if (liveStatus === "ended") {
      reload();
      onResetLive();
    }
  }, [liveStatus]);

  function handleUpload(file: File, title: string) {
    uploadAudio(file, title);
    setShowUploadModal(false);
  }

  function defaultMeetingTitle(): string {
    const d = new Date();
    return `${d.getMonth() + 1}월 ${d.getDate()}일 회의`;
  }

  function handleStartRecording() {
    setShowStartModal(true);
  }

  return (
    <div className="flex flex-1 overflow-hidden bg-recall-bgMain">
      {/* 왼쪽 회의 목록 패널 */}
      {!isMeetingListOpen ? (
        <button
          onClick={() => setIsMeetingListOpen(true)}
          title="회의 목록 펼치기"
          className="flex h-full w-8 flex-shrink-0 flex-col items-center justify-center gap-1.5 border-r border-recall-border text-recall-textMuted hover:bg-white/5"
        >
          <ChevronRightIcon size={13} />
          <span style={{ writingMode: "vertical-rl" }} className="text-xs">
            회의
          </span>
        </button>
      ) : (
        <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
          {/* 목록 패널 헤더 (타이틀 + 접기 버튼) */}
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-wider text-recall-textMuted">회의 목록</p>
            <button
              onClick={() => setIsMeetingListOpen(false)}
              title="회의 목록 접기"
              className="flex h-6 w-6 items-center justify-center rounded hover:bg-white/5 transition"
            >
              <ChevronLeftIcon size={13} className="text-recall-textMuted" />
            </button>
          </div>

          {/* 🌟 단일 메인 CTA 버튼: 새 회의 시작 */}
          <div className="mb-3 space-y-2">
            <button
              onClick={handleStartRecording}
              disabled={isLiveActive}
              title={isLiveActive ? "이미 진행 중인 회의가 있어요" : undefined}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-recall-accent py-3 px-4 text-sm font-bold text-white shadow-md shadow-recall-accent/25 hover:opacity-95 active:scale-95 transition-all disabled:cursor-not-allowed disabled:opacity-40"
            >
              <MicIcon size={16} />
              <span>+ 새 회의 시작</span>
            </button>

            {/* 보조 업로드 버튼 */}
            <button
              onClick={() => setShowUploadModal(true)}
              className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-recall-border bg-recall-bgSoft/60 py-2 text-xs font-semibold text-recall-textMuted hover:bg-white/5 hover:text-recall-text transition"
            >
              <UploadIcon size={13} />
              <span>음성 파일 업로드</span>
            </button>
          </div>

          {/* 회의 리스트 영역 */}
          <div className="flex-1 space-y-1.5 overflow-y-auto custom-scrollbar pr-0.5">
            {isLoading ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
            ) : meetings.length === 0 ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.meeting_none}</p>
            ) : (
              meetings.map((m) => {
                const isSelected = m.id === selectedMeetingId;
                const isThisLive = isLiveActive && liveMeeting && m.id === liveMeeting.id;
                const badge = statusBadge(m.status);
                return (
                  <div
                    key={m.id}
                    onClick={() => setSelectedMeetingId(m.id)}
                    className={`group flex cursor-pointer flex-col gap-1 rounded-xl border p-2.5 transition ${
                      isSelected
                        ? "border-recall-accent bg-recall-accent/10 shadow-sm"
                        : "border-recall-border/80 bg-recall-bgSoft/40 hover:bg-white/5"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      {m.input_type === "live_recording" ? (
                        <MicIcon
                          size={12}
                          className={`flex-shrink-0 ${isThisLive ? "text-recall-danger" : "text-recall-textMuted"}`}
                        />
                      ) : (
                        <DocumentIcon size={12} className="flex-shrink-0 text-recall-textMuted" />
                      )}
                      <span className="min-w-0 flex-1 truncate text-xs font-bold text-recall-text">
                        {m.title}
                      </span>
                      {!isThisLive && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            removeMeeting(m.id);
                          }}
                          className="hidden flex-shrink-0 text-recall-textMuted hover:text-recall-danger group-hover:inline transition"
                          aria-label="회의 삭제"
                        >
                          <TrashIcon size={12} />
                        </button>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      {isThisLive && (
                        <span className="h-1.5 w-1.5 flex-shrink-0 animate-pulse rounded-full bg-recall-danger" />
                      )}
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${badge.className}`}>
                        {isThisLive ? liveStatusLabel(liveStatus) : badge.label}
                      </span>
                      <span className="text-[11px] text-recall-textMuted">{formatDate(m.created_at)}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* 중앙 상세 메인 영역 */}
      <div className="flex h-full flex-1 flex-col p-4 overflow-hidden">
        {isViewingLive && liveMeeting ? (
          <>
            <div className="mb-3 flex items-center justify-between pb-3 border-b border-recall-border/60">
              <div>
                <EditableMeetingTitle title={liveMeeting.title} onRename={onRenameLive} />
                <p className="flex items-center gap-1.5 text-xs text-recall-textMuted mt-0.5">
                  {liveStatus === "recording" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 animate-pulse rounded-full bg-recall-danger" />
                  )}
                  {liveStatusLabel(liveStatus)}
                </p>
              </div>
              <div className="flex gap-1.5">
                {liveStatus === "recording" && (
                  <button
                    onClick={onPauseLive}
                    className="flex items-center gap-1.5 rounded-full border border-recall-border px-3 py-1.5 text-xs font-semibold text-recall-text hover:bg-white/5 transition"
                  >
                    <PauseIcon size={13} />
                    일시정지
                  </button>
                )}
                {liveStatus === "paused" && (
                  <button
                    onClick={onResumeLive}
                    className="flex items-center gap-1.5 rounded-full border border-recall-accent px-3 py-1.5 text-xs font-semibold text-recall-accent hover:bg-recall-accent/10 transition"
                  >
                    <PlayIcon size={13} />
                    재개
                  </button>
                )}
                {(liveStatus === "recording" || liveStatus === "paused") && (
                  <button
                    onClick={onStopLive}
                    className="flex items-center gap-1.5 rounded-full bg-red-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-red-500 transition shadow-md active:scale-95"
                  >
                    <StopIcon size={13} />
                    회의 종료
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto rounded-2xl border border-recall-border bg-white/5 p-4 custom-scrollbar">
              {liveStatus === "reconnecting" && (
                <div className="mb-2 flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                  <div className="h-3.5 w-3.5 flex-shrink-0 animate-spin rounded-full border-2 border-amber-500/30 border-t-amber-400" />
                  연결이 끊겨 재연결을 시도하고 있습니다...
                </div>
              )}
              {liveStatus === "connecting" || liveStatus === "ending" ? (
                <div className="flex h-full flex-col items-center justify-center gap-2">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                  <p className="text-xs text-recall-textMuted">{liveStatusLabel(liveStatus)}</p>
                </div>
              ) : liveSegments.length === 0 && !livePartial.confirmed && !livePartial.tentative ? (
                <p className="text-sm text-recall-textMuted">
                  {liveStatus === "paused" ? "일시정지 중입니다." : "말씀하시면 실시간으로 자막이 표시됩니다..."}
                </p>
              ) : (
                <div className="space-y-3 text-sm text-recall-textMuted">
                  <UnmappedSpeakerChips
                    labels={uniqueRawSpeakerLabels(liveSegments.map((s) => s.speaker_label))}
                    onAssign={onMapLiveSpeakers}
                  />
                  {liveSegments.map((s, i) => (
                    <SegmentRow
                      key={i}
                      speakerLabel={s.speaker_label}
                      timeMs={s.start_ms}
                      content={s.content}
                      hasContradiction={liveContradictionAlerts.some((a) => a.statement_text === s.content)}
                      t={t}
                    />
                  ))}
                  {(livePartial.confirmed || livePartial.tentative) && (
                    <p className="text-recall-textMuted">
                      <span className="font-medium text-recall-text">나</span> {livePartial.confirmed}
                      <span className="opacity-60">{livePartial.tentative}</span>
                    </p>
                  )}
                </div>
              )}
            </div>
          </>
        ) : liveStatus === "error" && !selectedRealMeeting ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3">
            <p className="text-sm text-recall-danger">{liveError || "오류가 발생했습니다."}</p>
            <button
              onClick={onResetLive}
              className="rounded-xl border border-recall-border px-4 py-2 text-xs font-semibold text-recall-text hover:bg-white/5 transition"
            >
              닫기
            </button>
          </div>
        ) : !selectedRealMeeting ? (
          /* 🌟 [개선됨] 선택된 회의가 없을 때: 중복 카드 제거 후 깔끔한 안내 텍스트만 표시 */
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-recall-textMuted text-2xl">
            </div>
            <p className="text-sm font-medium text-recall-textMuted">
              왼쪽 목록에서 회의를 선택하거나 <span className="text-recall-accent font-semibold">새 회의</span>를 시작하세요.
            </p>

            {joinableMeeting && (
              <div className="mt-2 flex flex-col items-center gap-2 rounded-2xl border border-recall-accent/40 bg-recall-accent/5 px-5 py-4">
                <p className="text-sm font-semibold text-recall-text">
                  "{joinableMeeting.title}" 회의가 각자 PC 모드로 진행 중이에요
                </p>
                <button
                  onClick={() => onJoinLive(joinableMeeting.id)}
                  className="rounded-xl bg-recall-accent px-4 py-2 text-xs font-semibold text-white hover:opacity-90 transition"
                >
                  참가하기
                </button>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="mb-3 flex items-start justify-between gap-2 pb-2 border-b border-recall-border/40">
              <div>
                <EditableMeetingTitle
                  title={selectedRealMeeting.title}
                  onRename={(title) => renameMeeting(selectedRealMeeting.id, title)}
                />
                <p className="text-xs text-recall-textMuted mt-0.5">
                  {statusBadge(selectedRealMeeting.status).label} · {formatDate(selectedRealMeeting.created_at)}
                  {selectedRealMeeting.duration_ms ? ` · ${formatDuration(selectedRealMeeting.duration_ms)}` : ""}
                </p>
              </div>
              <div className="flex flex-shrink-0 gap-1.5">
                <button
                  onClick={() => setShowAttendeesModal(true)}
                  className="flex items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5 transition"
                >
                  <PersonIcon size={12} />
                  참석자
                </button>
                <button
                  onClick={() => setShowExportModal(true)}
                  className="flex items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5 transition"
                >
                  <DocumentIcon size={12} />
                  회의록 내보내기
                </button>
              </div>
            </div>

            {selectedRealMeeting.status === "created" || selectedRealMeeting.status === "processing" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-2xl border border-recall-border bg-white/5">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                <p className="text-xs text-recall-textMuted">{t.meeting_processing}</p>
              </div>
            ) : selectedRealMeeting.status === "failed" ? (
              <div className="flex flex-1 items-center justify-center rounded-2xl border border-recall-danger/30 bg-recall-danger/5">
                <p className="text-xs text-recall-danger">{t.meeting_failed}</p>
              </div>
            ) : (
              <>
                <div className="mb-3 flex gap-2 border-b border-recall-border">
                  {(
                    [
                      { key: "summary", label: t.meeting_tab_summary },
                      { key: "minutes", label: t.meeting_tab_minutes },
                      { key: "script", label: t.meeting_tab_script },
                    ] as { key: DetailTab; label: string }[]
                  ).map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setDetailTab(tab.key)}
                      className={`px-3 py-1.5 text-xs font-semibold transition ${
                        detailTab === tab.key
                          ? "border-b-2 border-recall-accent text-recall-accent"
                          : "text-recall-textMuted hover:text-recall-text"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div className="flex-1 overflow-y-auto rounded-2xl border border-recall-border bg-white/5 p-4 custom-scrollbar">
                  {isDetailLoading ? (
                    <p className="text-xs text-recall-textMuted">{t.common_loading}</p>
                  ) : detailTab === "summary" ? (
                    summary?.generation_status === "completed" ? (
                      <div className="space-y-4">
                        {summary.short_summary && (
                          <div className="p-3.5 rounded-xl bg-recall-accent/10 border border-recall-accent/20">
                            <p className="text-xs font-bold text-recall-accent uppercase mb-1">한 줄 요약</p>
                            <p className="text-sm font-bold text-recall-text">{summary.short_summary}</p>
                          </div>
                        )}
                        {summary.full_summary && (
                          <p className="whitespace-pre-line text-xs leading-relaxed text-recall-textMuted p-3.5 rounded-xl bg-white/5 border border-recall-border/30">
                            {summary.full_summary}
                          </p>
                        )}
                        {decisions.length > 0 && (
                          <div className="border-t border-recall-border pt-3">
                            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-recall-textMuted">
                              {t.meeting_summary_key_decisions}
                            </p>
                            <ul className="space-y-1.5">
                              {decisions.map((d) => (
                                <li key={d.id} className="flex gap-2 text-xs text-recall-text p-2 rounded-lg bg-white/5">
                                  <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-accent" />
                                  <span>
                                    <span className="font-bold">{d.title}</span>
                                    <span className="text-recall-textMuted"> — {d.decision_text}</span>
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-recall-textMuted">{t.meeting_summary_not_ready}</p>
                    )
                  ) : detailTab === "minutes" ? (
                    (() => {
                      const { initial: initialAttendees, added: addedAttendees } = groupAttendees(attendees);
                      return (
                        <div className="space-y-4 text-xs">
                          <div>
                            <p className="text-sm font-bold text-recall-text">{selectedRealMeeting.title}</p>
                            <p className="mt-0.5 text-recall-textMuted">
                              {formatDateOnly(selectedRealMeeting.started_at ?? selectedRealMeeting.created_at)} ·{" "}
                              {formatTimeOnly(selectedRealMeeting.started_at ?? selectedRealMeeting.created_at)}
                            </p>
                          </div>

                          <div className="grid grid-cols-2 gap-3 border-t border-recall-border pt-3">
                            <div>
                              <p className="mb-1 font-semibold text-recall-textMuted">
                                {t.meeting_minutes_mode_label}
                              </p>
                              <p className="text-recall-text">
                                {selectedRealMeeting.is_online === true
                                  ? t.meeting_minutes_mode_online
                                  : selectedRealMeeting.is_online === false
                                    ? t.meeting_minutes_mode_offline
                                    : t.meeting_minutes_mode_unset}
                              </p>
                            </div>
                            <div>
                              <p className="mb-1 font-semibold text-recall-textMuted">
                                {t.meeting_minutes_location_label}
                              </p>
                              <p className="text-recall-text">
                                {selectedRealMeeting.location || t.meeting_minutes_datetime_unset}
                              </p>
                            </div>
                          </div>

                          <div className="border-t border-recall-border pt-3">
                            <p className="mb-1 font-semibold text-recall-textMuted">
                              {t.meeting_minutes_attendees_initial}
                            </p>
                            {initialAttendees.length === 0 ? (
                              <p className="text-recall-textMuted">{t.meeting_minutes_attendees_none}</p>
                            ) : (
                              <p className="text-recall-text">
                                {initialAttendees.map((a) => a.display_name).join(", ")}
                              </p>
                            )}
                            <p className="mb-1 mt-3 font-semibold text-recall-textMuted">
                              {t.meeting_minutes_attendees_added}
                            </p>
                            {addedAttendees.length === 0 ? (
                              <p className="text-recall-textMuted">{t.meeting_minutes_attendees_none_added}</p>
                            ) : (
                              <p className="text-recall-text">
                                {addedAttendees.map((a) => a.display_name).join(", ")}
                              </p>
                            )}
                          </div>

                          <div className="border-t border-recall-border pt-3">
                            <p className="mb-1 font-semibold text-recall-textMuted">
                              {t.meeting_minutes_content_label}
                            </p>
                            {summary?.full_summary ? (
                              <p className="whitespace-pre-line text-recall-text leading-relaxed">
                                {summary.full_summary}
                              </p>
                            ) : (
                              <p className="text-recall-textMuted">{t.meeting_minutes_content_empty}</p>
                            )}
                          </div>
                        </div>
                      );
                    })()
                  ) : segments.length === 0 ? (
                    <p className="text-xs text-recall-textMuted">{t.meeting_no_script}</p>
                  ) : (
                    <div className="space-y-3 text-xs text-recall-textMuted">
                      <UnmappedSpeakerChips
                        labels={uniqueRawSpeakerLabels(segments.map((s) => s.speaker_label))}
                        onAssign={mapSpeakerNames}
                      />
                      {segments
                        .slice()
                        .sort((a, b) => a.segment_index - b.segment_index)
                        .map((s) => (
                          <SegmentRow
                            key={s.id}
                            speakerLabel={s.speaker_label}
                            timeMs={s.start_ms}
                            content={s.content}
                            t={t}
                          />
                        ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </>
        )}
      </div>

      {/* 오른쪽 모순 감지 목록 패널 */}
      {!isContradictionListOpen ? (
        <button
          onClick={() => setIsContradictionListOpen(true)}
          title="모순 목록 펼치기"
          className="group relative flex h-full w-8 flex-shrink-0 flex-col items-center gap-2 border-l border-recall-border py-3 text-recall-textMuted transition-colors hover:border-recall-danger/40 hover:bg-white/5"
        >
          <span className="relative">
            <WarningIcon
              size={16}
              className={contradictions.length > 0 ? "text-recall-danger" : "text-recall-textMuted"}
            />
            {contradictions.length > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-recall-danger text-[10px] font-semibold text-white">
                {contradictions.length}
              </span>
            )}
          </span>
          <ChevronLeftIcon size={11} className="opacity-50 transition-opacity group-hover:opacity-100" />
        </button>
      ) : (
        <div className="flex h-full w-72 flex-shrink-0 flex-col border-l border-recall-border p-3">
          <div className="mb-2 flex items-center gap-1.5">
            <button
              onClick={() => setIsContradictionListOpen(false)}
              title="모순 목록 접기"
              className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded hover:bg-white/5"
            >
              <ChevronRightIcon size={13} className="text-recall-textMuted" />
            </button>
            <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-recall-textMuted">
              <WarningIcon size={12} className="text-recall-danger" />
              {t.contradiction_title}
            </p>
          </div>

          {isViewingLive ? (
            <p className="mb-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-2.5 py-2 text-xs text-amber-400">
              녹음 중에는 확인만 하고, 회의가 끝난 뒤 처리할 수 있어요.
            </p>
          ) : (
            <div className="mb-2 flex gap-1 rounded-xl border border-recall-border bg-recall-bgSoft p-1">
              {(
                [
                  { key: "unresolved" as const, label: t.contradiction_status_unresolved },
                  { key: "resolved" as const, label: t.contradiction_status_resolved },
                ]
              ).map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setContradictionStatusFilter(tab.key)}
                  className={`flex-1 rounded-lg py-1 text-xs font-semibold transition ${
                    contradictionStatusFilter === tab.key
                      ? "bg-recall-accent text-white"
                      : "text-recall-textMuted hover:text-recall-text"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}

          <div className="flex-1 space-y-2 overflow-y-auto custom-scrollbar pr-0.5">
            {isContradictionsLoading ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
            ) : contradictions.length === 0 ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.contradiction_none}</p>
            ) : (
              contradictions.map((c) => {
                const isExpanded = expandedContradictionIds.has(c.id);
                return (
                  <div
                    key={c.id}
                    onClick={() => toggleContradictionExpanded(c.id)}
                    className="cursor-pointer rounded-xl border border-recall-border/80 bg-recall-bgSoft/40 p-2.5 hover:border-recall-accent/50 transition"
                  >
                    <div className="mb-1 flex items-center justify-between gap-1">
                      <span className="flex items-center gap-1 text-[11px] font-medium text-recall-textMuted">
                        {c.source_type === "meeting_segment" ? (
                          <MicIcon size={11} className="flex-shrink-0" />
                        ) : (
                          <DocumentIcon size={11} className="flex-shrink-0" />
                        )}
                        {c.source_type === "meeting_segment" ? t.contradiction_source_meeting : t.contradiction_source_chat}
                      </span>
                      {severityBadge(c.severity, t)}
                    </div>
                    <ContradictionMessage
                      contradiction={c}
                      expanded={isExpanded}
                      onViewReference={(id, name) => setPreviewDoc({ id, name })}
                      t={t}
                    />
                    {!isViewingLive && (
                      <div className="flex gap-1 pt-1" onClick={(e) => e.stopPropagation()}>
                        {c.status === "unresolved" ? (
                          <>
                            <button
                              onClick={() => dismiss(c.id)}
                              className="flex-1 rounded border border-recall-border px-1.5 py-1 text-[11px] text-recall-textMuted hover:bg-white/5"
                            >
                              {t.contradiction_dismiss}
                            </button>
                            <button
                              onClick={() => resolve(c.id, "keep_reference")}
                              className="flex-1 rounded border border-recall-border px-1.5 py-1 text-[11px] text-recall-text hover:bg-white/5"
                            >
                              {t.contradiction_keep}
                            </button>
                            <button
                              onClick={() => resolve(c.id, "change_acknowledged")}
                              className="flex-1 rounded bg-recall-accent px-1.5 py-1 text-[11px] font-medium text-white hover:opacity-90"
                            >
                              {t.contradiction_apply}
                            </button>
                          </>
                        ) : (
                          c.resolution_type !== "change_acknowledged" && (
                            <button
                              onClick={() => reopen(c.id)}
                              className="flex-1 rounded border border-recall-border px-1.5 py-1 text-[11px] text-recall-textMuted hover:bg-white/5"
                            >
                              {t.contradiction_reopen}
                            </button>
                          )
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* 모달 연동 */}
      {showUploadModal && (
        <UploadModal
          isUploading={isUploading}
          onClose={() => setShowUploadModal(false)}
          onUpload={handleUpload}
        />
      )}

      {pendingSummaryFor && (
        <ChangeSummaryModal
          contradiction={pendingSummaryFor}
          changeSummary={changeSummary}
          isLoading={isChangeSummaryLoading}
          onClose={closeChangeSummary}
          t={t}
        />
      )}

      {previewDoc && (
        <DocumentPreviewModal
          workspaceId={workspaceId}
          documentId={previewDoc.id}
          documentName={previewDoc.name}
          onClose={() => setPreviewDoc(null)}
        />
      )}

      {showAttendeesModal && selectedRealMeeting && (
        <MeetingAttendeesModal
          workspaceId={workspaceId}
          meetingId={selectedRealMeeting.id}
          meetingTitle={selectedRealMeeting.title}
          onClose={() => setShowAttendeesModal(false)}
          onSaved={reloadAttendees}
        />
      )}

      {showExportModal && selectedRealMeeting && (
        <MeetingExportModal
          workspaceId={workspaceId}
          meetingId={selectedRealMeeting.id}
          onClose={() => setShowExportModal(false)}
        />
      )}

      {showStartModal && (
        <MeetingStartModal
          workspaceId={workspaceId}
          defaultTitle={defaultMeetingTitle()}
          onClose={() => setShowStartModal(false)}
          onStart={(title, attendeeIds, location, recordingMode) => {
            setShowStartModal(false);
            onStartLive(title, undefined, attendeeIds, location, recordingMode);
          }}
        />
      )}
    </div>
  );
}