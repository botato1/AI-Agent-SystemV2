import { useEffect, useRef, useState } from "react";
import { useRealMeetings } from "../hooks/useRealMeetings";
import { LiveMeetingStatus, LiveSegment, ContradictionAlert } from "../hooks/useLiveMeeting";
import { useContradictions } from "../hooks/useContradictions";
import { Meeting, MeetingStatus } from "../services/meeting";
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
} from "./icons";
import ContradictionMessage from "./ContradictionMessage";
import ChangeSummaryModal from "./ChangeSummaryModal";

function severityBadge(severity: ContradictionSeverity, t: any) {
  const map = {
    high: { label: t.priority_high, className: "bg-recall-danger/15 text-recall-danger" },
    medium: { label: t.priority_medium, className: "bg-amber-500/15 text-amber-400" },
    low: { label: t.priority_low, className: "bg-recall-textMuted/15 text-recall-textMuted" },
  } as const;
  const { label, className } = map[severity];
  return <span className={`flex-shrink-0 rounded-full px-1.5 py-0.5 text-[11px] ${className}`}>{label}</span>;
}

type DetailTab = "summary" | "decisions" | "script";

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

// STT가 준 원본 화자 라벨인지(아직 실명으로 매핑 안 됐는지) 판단
function isRawSpeakerLabel(label: string | null | undefined): label is string {
  return !!label && /^SPEAKER[_\s]?\d+$/i.test(label.trim());
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
  onStartLive: (title: string) => void;
  onPauseLive: () => void;
  onResumeLive: () => void;
  onStopLive: () => void;
  onResetLive: () => void;
  onMapLiveSpeakers: (mapping: Record<string, string>) => void;
  onRenameLive: (title: string) => void;
  t: any;
}

// 회의 제목 인라인 수정 — 클릭하면 입력창으로 바뀌고, Enter/blur로 저장
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

// 아직 실명 매핑 안 된 화자 라벨을 칩으로 보여주고, 누르면 이름을 물어봐서 매핑 API를 호출한다.
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
  onStartLive,
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
    resolve,
    dismiss,
    refresh: refreshContradictions,
    pendingSummaryFor,
    changeSummary,
    isChangeSummaryLoading,
    closeChangeSummary,
  } = useContradictions(workspaceId);

  // 실시간 회의 중 모순 감지 WS 알림이 오면, 8초 폴링을 기다리지 않고 즉시 목록을 새로고침
  const prevAlertCountRef = useRef(liveContradictionAlerts.length);
  useEffect(() => {
    if (liveContradictionAlerts.length > prevAlertCountRef.current) {
      refreshContradictions();
    }
    prevAlertCountRef.current = liveContradictionAlerts.length;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveContradictionAlerts.length]);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("summary");
  const [isMeetingListOpen, setIsMeetingListOpen] = useState(true);
  const [isContradictionListOpen, setIsContradictionListOpen] = useState(true);
  const [expandedContradictionIds, setExpandedContradictionIds] = useState<Set<string>>(new Set());

  function toggleContradictionExpanded(id: string) {
    setExpandedContradictionIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const isLiveActive = LIVE_ACTIVE_STATUSES.includes(liveStatus);

  // 녹음 중인 회의도 목록의 일반 항목과 똑같이 취급 - id가 같으면 실제 목록 값을 덮어써서 하나로만 보인다
  const meetings: Meeting[] =
    isLiveActive && liveMeeting
      ? [liveMeeting, ...realMeetings.filter((m) => m.id !== liveMeeting.id)]
      : realMeetings;

  const isViewingLive = isLiveActive && !!liveMeeting && selectedMeetingId === liveMeeting.id;

  // 회의 발언 쪽 모순만 보여주고(채팅 메시지 쪽은 채팅방 화면에서 따로 보여줌), 그중에서도
  // 지금 보고 있는 회의(실시간 or 선택된 과거 회의) 것만 걸러서 보여준다 — 다른 회의 갔다와도
  // 안 섞이고, 새 회의 들어가면 그 회의 것만 보이도록.
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

  // 닫혀 있는 동안 새 모순이 감지되면 자동으로 펼침
  useEffect(() => {
    if (contradictions.length > prevContradictionCountRef.current) {
      setIsContradictionListOpen((prevOpen) => (prevOpen ? prevOpen : true));
    }
    prevContradictionCountRef.current = contradictions.length;
  }, [contradictions.length]);

  // 새 녹음이 시작되면 그 회의를 자동으로 선택
  useEffect(() => {
    if (isLiveActive && liveMeeting) {
      setSelectedMeetingId(liveMeeting.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLiveActive, liveMeeting?.id]);

  // 녹음이 끝나면(ended) 실제 목록을 새로고침해서 같은 회의를 이어서 보여준다 (선택은 그대로 유지됨)
  useEffect(() => {
    if (liveStatus === "ended") {
      reload();
      onResetLive();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveStatus]);

  function handleUpload(file: File, title: string) {
    uploadAudio(file, title);
    setShowUploadModal(false);
  }

  function handleStartRecording() {
    const liveCount = realMeetings.filter((m) => m.input_type === "live_recording").length;
    onStartLive(`새 녹음 ${liveCount + 1}`);
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* 왼쪽 목록 */}
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
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium uppercase tracking-wide text-recall-textMuted">회의</p>
          <div className="flex gap-1">
            <button
              onClick={handleStartRecording}
              disabled={isLiveActive}
              title={isLiveActive ? "이미 녹음이 진행 중이에요" : undefined}
              className="flex items-center gap-1 rounded-lg border border-recall-border px-2 py-1 text-xs text-recall-text hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <MicIcon size={12} />
              새 녹음
            </button>
            <button
              onClick={() => setShowUploadModal(true)}
              className="flex items-center gap-1 rounded-lg border border-recall-border px-2 py-1 text-xs text-recall-text hover:bg-white/5"
            >
              <UploadIcon size={12} />
              업로드
            </button>
            <button
              onClick={() => setIsMeetingListOpen(false)}
              title="회의 목록 접기"
              className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded hover:bg-white/5"
            >
              <ChevronLeftIcon size={13} className="text-recall-textMuted" />
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-1.5 overflow-y-auto">
          {isLoading ? (
            <p className="text-sm text-recall-textMuted">{t.common_loading}</p>
          ) : meetings.length === 0 ? (
            <p className="text-sm text-recall-textMuted">{t.meeting_none}</p>
          ) : (
            meetings.map((m) => {
              const isSelected = m.id === selectedMeetingId;
              const isThisLive = isLiveActive && liveMeeting && m.id === liveMeeting.id;
              const badge = statusBadge(m.status);
              return (
                <div
                  key={m.id}
                  onClick={() => setSelectedMeetingId(m.id)}
                  className={`group flex cursor-pointer flex-col gap-1 rounded-lg border px-2.5 py-2 ${
                    isSelected
                      ? "border-recall-accent bg-recall-accent/10"
                      : "border-recall-border hover:bg-white/5"
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
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-recall-text">
                      {m.title}
                    </span>
                    {!isThisLive && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeMeeting(m.id);
                        }}
                        className="hidden flex-shrink-0 text-recall-textMuted hover:text-recall-danger group-hover:inline"
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
                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${badge.className}`}>
                      {isThisLive ? liveStatusLabel(liveStatus) : badge.label}
                    </span>
                    <span className="text-xs text-recall-textMuted">{formatDate(m.created_at)}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
      )}

      {/* 오른쪽 상세 */}
      <div className="flex h-full flex-1 flex-col p-4">
        {isViewingLive && liveMeeting ? (
          <>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <EditableMeetingTitle title={liveMeeting.title} onRename={onRenameLive} />
                <p className="flex items-center gap-1.5 text-sm text-recall-textMuted">
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
                    className="flex items-center gap-1.5 rounded-lg border border-recall-border px-2.5 py-1.5 text-sm text-recall-text hover:bg-white/5"
                  >
                    <PauseIcon size={13} />
                    일시정지
                  </button>
                )}
                {liveStatus === "paused" && (
                  <button
                    onClick={onResumeLive}
                    className="flex items-center gap-1.5 rounded-lg border border-recall-border px-2.5 py-1.5 text-sm text-recall-text hover:bg-white/5"
                  >
                    <PlayIcon size={13} />
                    재개
                  </button>
                )}
                {(liveStatus === "recording" || liveStatus === "paused") && (
                  <button
                    onClick={onStopLive}
                    className="flex items-center gap-1.5 rounded-lg border border-recall-danger px-2.5 py-1.5 text-sm font-medium text-recall-danger"
                  >
                    <StopIcon size={13} />
                    종료
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
              {liveStatus === "reconnecting" && (
                <div className="mb-2 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-400">
                  <div className="h-3.5 w-3.5 flex-shrink-0 animate-spin rounded-full border-2 border-amber-500/30 border-t-amber-400" />
                  연결이 끊겨 재연결을 시도하고 있습니다...
                </div>
              )}
              {liveStatus === "connecting" || liveStatus === "ending" ? (
                <div className="flex h-full flex-col items-center justify-center gap-2">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                  <p className="text-sm text-recall-textMuted">{liveStatusLabel(liveStatus)}</p>
                </div>
              ) : liveSegments.length === 0 && !livePartial.confirmed && !livePartial.tentative ? (
                <p className="text-base text-recall-textMuted">
                  {liveStatus === "paused" ? "일시정지 중입니다." : "말씀하시면 실시간으로 자막이 표시됩니다..."}
                </p>
              ) : (
                <div className="space-y-2 text-base text-recall-textMuted">
                  <UnmappedSpeakerChips
                    labels={uniqueRawSpeakerLabels(liveSegments.map((s) => s.speaker_label))}
                    onAssign={onMapLiveSpeakers}
                  />
                  {liveSegments.map((s, i) => (
                    <p key={i}>
                      <span className="font-medium text-recall-text">{s.speaker_label || t.speaker_unknown}</span>{" "}
                      {s.content}
                    </p>
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
            <p className="text-base text-recall-danger">{liveError || "오류가 발생했습니다."}</p>
            <button
              onClick={onResetLive}
              className="rounded-lg border border-recall-border px-3.5 py-2 text-sm text-recall-text hover:bg-white/5"
            >
              닫기
            </button>
          </div>
        ) : !selectedRealMeeting ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-base text-recall-textMuted">왼쪽에서 회의를 선택하거나 새로 시작하세요.</p>
          </div>
        ) : (
          <>
            <div className="mb-3">
              <EditableMeetingTitle
                title={selectedRealMeeting.title}
                onRename={(title) => renameMeeting(selectedRealMeeting.id, title)}
              />
              <p className="text-sm text-recall-textMuted">
                {statusBadge(selectedRealMeeting.status).label} · {formatDate(selectedRealMeeting.created_at)}
                {selectedRealMeeting.duration_ms ? ` · ${formatDuration(selectedRealMeeting.duration_ms)}` : ""}
              </p>
            </div>

            {selectedRealMeeting.status === "created" || selectedRealMeeting.status === "processing" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-recall-border">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                <p className="text-base text-recall-textMuted">{t.meeting_processing}</p>
              </div>
            ) : selectedRealMeeting.status === "failed" ? (
              <div className="flex flex-1 items-center justify-center rounded-lg border border-recall-danger/30 bg-recall-danger/5">
                <p className="text-base text-recall-danger">{t.meeting_failed}</p>
              </div>
            ) : (
              <>
                <div className="mb-3 flex gap-0.5 border-b border-recall-border">
                  {(
                    [
                      { key: "summary", label: t.meeting_tab_summary },
                      { key: "decisions", label: t.meeting_tab_decisions },
                      { key: "script", label: t.meeting_tab_script },
                    ] as { key: DetailTab; label: string }[]
                  ).map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setDetailTab(tab.key)}
                      className={`px-2 py-1 text-sm ${
                        detailTab === tab.key
                          ? "border-b-2 border-recall-accent text-recall-text"
                          : "text-recall-textMuted hover:text-recall-text"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
                  {isDetailLoading ? (
                    <p className="text-base text-recall-textMuted">{t.common_loading}</p>
                  ) : detailTab === "summary" ? (
                    summary?.generation_status === "completed" ? (
                      <div className="space-y-3">
                        {summary.short_summary && (
                          <p className="text-base font-medium text-recall-text">{summary.short_summary}</p>
                        )}
                        {summary.full_summary && (
                          <p className="whitespace-pre-line text-base text-recall-textMuted">
                            {summary.full_summary}
                          </p>
                        )}
                      </div>
                    ) : (
                      <p className="text-base text-recall-textMuted">{t.meeting_summary_not_ready}</p>
                    )
                  ) : detailTab === "decisions" ? (
                    decisions.length === 0 ? (
                      <p className="text-base text-recall-textMuted">{t.meeting_no_decisions}</p>
                    ) : (
                      <div className="space-y-3">
                        {decisions.map((d) => (
                          <div key={d.id} className="rounded-lg border border-recall-border p-2.5">
                            <p className="text-base font-medium text-recall-text">{d.title}</p>
                            <p className="mt-1 text-sm text-recall-textMuted">{d.decision_text}</p>
                            {d.reason && (
                              <p className="mt-1 text-xs text-recall-textMuted">
                                {t.decision_reason_label} {d.reason}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )
                  ) : segments.length === 0 ? (
                    <p className="text-base text-recall-textMuted">{t.meeting_no_script}</p>
                  ) : (
                    <div className="space-y-2 text-base text-recall-textMuted">
                      <UnmappedSpeakerChips
                        labels={uniqueRawSpeakerLabels(segments.map((s) => s.speaker_label))}
                        onAssign={mapSpeakerNames}
                      />
                      {segments
                        .slice()
                        .sort((a, b) => a.segment_index - b.segment_index)
                        .map((s) => (
                          <p key={s.id}>
                            <span className="font-medium text-recall-text">
                              {s.speaker_label || t.speaker_unknown}
                            </span>{" "}
                            {s.content}
                          </p>
                        ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </>
        )}
      </div>

      {/* 오른쪽 모순 감지 목록 (채팅+회의 통합) */}
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
            <p className="flex items-center gap-1.5 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
              <WarningIcon size={12} className="text-recall-danger" />
              {t.contradiction_title}
            </p>
          </div>

          <div className="flex-1 space-y-2 overflow-y-auto">
            {isContradictionsLoading ? (
              <p className="text-sm text-recall-textMuted">{t.common_loading}</p>
            ) : contradictions.length === 0 ? (
              <p className="text-sm text-recall-textMuted">{t.contradiction_none}</p>
            ) : (
              contradictions.map((c) => {
                const isExpanded = expandedContradictionIds.has(c.id);
                return (
                <div
                  key={c.id}
                  onClick={() => toggleContradictionExpanded(c.id)}
                  className="cursor-pointer rounded-lg border border-recall-border p-2.5 hover:border-recall-accent/40"
                >
                  <div className="mb-1 flex items-center justify-between gap-1">
                    <span className="flex items-center gap-1 text-xs font-medium text-recall-textMuted">
                      {c.source_type === "meeting_segment" ? (
                        <MicIcon size={11} className="flex-shrink-0" />
                      ) : (
                        <DocumentIcon size={11} className="flex-shrink-0" />
                      )}
                      {c.source_type === "meeting_segment" ? t.contradiction_source_meeting : t.contradiction_source_chat}
                    </span>
                    {severityBadge(c.severity, t)}
                  </div>
                  <ContradictionMessage contradiction={c} expanded={isExpanded} t={t} />
                  <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => dismiss(c.id)}
                      className="flex-1 rounded border border-recall-border px-1.5 py-1 text-xs text-recall-textMuted hover:bg-white/5"
                    >
                      {t.contradiction_dismiss}
                    </button>
                    <button
                      onClick={() => resolve(c.id, "keep_reference")}
                      className="flex-1 rounded border border-recall-border px-1.5 py-1 text-xs text-recall-text hover:bg-white/5"
                    >
                      {t.contradiction_keep}
                    </button>
                    <button
                      onClick={() => resolve(c.id, "change_acknowledged")}
                      className="flex-1 rounded bg-recall-accent px-1.5 py-1 text-xs font-medium text-white hover:opacity-90"
                    >
                      {t.contradiction_apply}
                    </button>
                  </div>
                </div>
                );
              })
            )}
          </div>
        </div>
      )}

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
    </div>
  );
}
