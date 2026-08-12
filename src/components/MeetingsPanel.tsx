import { useEffect, useRef, useState } from "react";
import { useRealMeetings } from "../hooks/useRealMeetings";
import { useCategories } from "../hooks/useCategories";
import { LiveMeetingStatus, LiveSegment, ContradictionAlert, ContradictionAlertAction, AudioQualityAlert } from "../hooks/useLiveMeeting";
import { useContradictions } from "../hooks/useContradictions";
import { useDecisionReminders } from "../hooks/useDecisionReminders";
import { Meeting, MeetingStatus, RecordingMode, AgendaReminderPopup, AgendaReminderItem, Decision } from "../services/meeting";
import { ContradictionSeverity, ContradictionResolutionType } from "../services/contradiction";
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
  ChevronDownIcon,
  WarningIcon,
  AssistIcon,
  PencilIcon,
  PersonIcon,
  DownloadIcon,
  RepeatIcon,
  CloseIcon,
  HeadphoneIcon,
  SplitIcon,
  CheckIcon,
  PlusIcon,
} from "./icons";
import ContradictionMessage from "./ContradictionMessage";
import ContradictionEditForm from "./ContradictionEditForm";
import { showConfirm } from "../lib/confirm";
import ChangeSummaryModal from "./ChangeSummaryModal";
import DocumentPreviewModal from "./DocumentPreviewModal";
import MeetingAttendeesModal from "./MeetingAttendeesModal";
import MeetingExportModal from "./MeetingExportModal";
import MeetingStartModal from "./MeetingStartModal";
import SplitSegmentModal from "./SplitSegmentModal";
import MeetingAudioPlayer, { MeetingAudioPlayerHandle } from "./MeetingAudioPlayer";
import Avatar from "./Avatar";
import { hashAvatarColor } from "../data/avatarColors";
import { getVoiceProfileListApi } from "../services/voice";
import { getMeetingExportsApi, MeetingExportRecord, SplitSegmentParams } from "../services/meeting";
import { getDocumentFileApi } from "../services/document";

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

// 결정 리마인더 + 모순/결정변경 감지 - 회의 중 뜨는 알림을 한 큐로 합쳐서 한 번에 하나씩 보여준다
type LiveAlertQueueItem =
  | { kind: "agenda"; id: string; item: AgendaReminderItem }
  | { kind: "contradiction"; id: string; alert: ContradictionAlert };

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

function isRawSpeakerLabel(label: string | null | undefined): label is string {
  return !!label && /^SPEAKER[_\s]?\d+$/i.test(label.trim());
}

function AssignSpeakerControl({
  nameOptions,
  onAssign,
  t,
}: {
  nameOptions: string[];
  onAssign: (name: string) => void;
  t: any;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const datalistId = useRef(`speaker-options-${Math.random().toString(36).slice(2)}`).current;

  function commit() {
    const trimmed = draft.trim();
    if (trimmed) onAssign(trimmed);
    setIsEditing(false);
    setDraft("");
  }

  if (!isEditing) {
    return (
      <button
        onClick={() => setIsEditing(true)}
        className="text-xs text-recall-accent underline hover:opacity-80"
      >
        {t.meeting_speaker_assign_btn}
      </button>
    );
  }

  return (
    <span className="inline-flex items-center gap-1">
      <input
        autoFocus
        list={datalistId}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") {
            setIsEditing(false);
            setDraft("");
          }
        }}
        placeholder={t.meeting_speaker_assign_placeholder}
        className="w-28 rounded border border-recall-border bg-transparent px-1.5 py-0.5 text-xs text-recall-text outline-none focus:border-recall-accent"
      />
      <datalist id={datalistId}>
        {nameOptions.map((n) => (
          <option key={n} value={n} />
        ))}
      </datalist>
      <button
        onClick={commit}
        disabled={!draft.trim()}
        className="text-xs font-semibold text-recall-accent disabled:opacity-40"
      >
        {t.btn_confirm}
      </button>
    </span>
  );
}

function SegmentRow({
  speakerLabel,
  avatarImageUrl,
  timeMs,
  content,
  hasContradiction,
  segmentId,
  speakerNameOptions,
  onAssignSpeaker,
  onEditContent,
  onSeekAudio,
  onSplit,
  bulkEditValue,
  onBulkEditChange,
  t,
}: {
  speakerLabel: string | null | undefined;
  avatarImageUrl?: string | null;
  timeMs: number;
  content: string;
  hasContradiction?: boolean;
  segmentId?: string;
  speakerNameOptions?: string[];
  onAssignSpeaker?: (segmentId: string, name: string) => void;
  onEditContent?: (segmentId: string, content: string) => Promise<boolean>;
  onSeekAudio?: (timeMs: number) => void;
  onSplit?: (segmentId: string) => void;
  // 전체 수정 모드 - 값이 주어지면(undefined가 아니면) 개별 수정/분할 UI 대신 항상 열려있는
  // textarea 하나만 보여준다. 저장/취소는 상위(MeetingsPanel)에서 한 번에 처리한다.
  bulkEditValue?: string;
  onBulkEditChange?: (value: string) => void;
  t: any;
}) {
  const name = speakerLabel || t.speaker_unknown;
  const isIdentified = !!speakerLabel && !isRawSpeakerLabel(speakerLabel);
  const canAssign = !speakerLabel && !!segmentId && !!onAssignSpeaker;
  const canEditContent = !!segmentId && !!onEditContent;
  const canSplit = !!segmentId && !!onSplit;
  const isBulkEditing = bulkEditValue !== undefined;

  const [isEditingContent, setIsEditingContent] = useState(false);
  const [draft, setDraft] = useState(content);
  const [isSaving, setIsSaving] = useState(false);

  async function handleSave() {
    if (!segmentId || !onEditContent) return;
    const trimmed = draft.trim();
    if (!trimmed || trimmed === content) {
      setIsEditingContent(false);
      return;
    }
    setIsSaving(true);
    const ok = await onEditContent(segmentId, trimmed);
    setIsSaving(false);
    if (ok) setIsEditingContent(false);
  }

  return (
    <div className={`group flex gap-2 rounded-lg ${hasContradiction ? "-mx-1.5 border border-recall-danger/30 bg-recall-danger/5 px-1.5 py-1" : ""}`}>
      {isIdentified ? (
        <Avatar
          user={{ name, avatarColor: hashAvatarColor(name), avatarImageUrl: avatarImageUrl ?? null }}
          size={24}
          className="mt-0.5 text-[11px] font-semibold"
        />
      ) : (
        <div className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-recall-border text-recall-textMuted">
          <PersonIcon size={13} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-1.5">
          <span className={`font-medium ${isIdentified ? "text-recall-text" : "text-recall-textMuted"}`}>
            {name}
          </span>
          {onSeekAudio ? (
            <button
              onClick={() => onSeekAudio(timeMs)}
              title={t.meeting_audio_seek_title}
              className="text-xs text-recall-textMuted/70 underline decoration-dotted hover:text-recall-accent"
            >
              {formatDuration(timeMs)}
            </button>
          ) : (
            <span className="text-xs text-recall-textMuted/70">{formatDuration(timeMs)}</span>
          )}
          {hasContradiction && (
            <AssistIcon size={12} className="flex-shrink-0 text-recall-accent" />
          )}
          {canAssign && (
            <AssignSpeakerControl
              nameOptions={speakerNameOptions ?? []}
              onAssign={(assignedName) => onAssignSpeaker!(segmentId!, assignedName)}
              t={t}
            />
          )}
        </p>
        {isBulkEditing ? (
          <textarea
            value={bulkEditValue}
            onChange={(e) => onBulkEditChange?.(e.target.value)}
            rows={2}
            className="mt-1 w-full rounded-lg border border-recall-border bg-recall-bgMain px-2.5 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
          />
        ) : isEditingContent ? (
          <div className="mt-1 flex flex-col gap-1.5">
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2.5 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
            />
            <div className="flex justify-end gap-1.5">
              <button
                onClick={() => {
                  setDraft(content);
                  setIsEditingContent(false);
                }}
                disabled={isSaving}
                className="rounded border border-recall-border px-2 py-1 text-[11px] text-recall-textMuted hover:bg-white/5 disabled:opacity-50"
              >
                {t.task_cancel}
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving || !draft.trim()}
                className="rounded bg-recall-accent px-2 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
              >
                {isSaving ? t.meeting_export_saving : t.task_save}
              </button>
            </div>
          </div>
        ) : (
          <p className="flex items-start gap-1.5 text-recall-textMuted">
            <span className="flex-1">{content}</span>
            {canSplit && (
              <button
                onClick={() => onSplit!(segmentId!)}
                title={t.meeting_split_btn}
                className="flex-shrink-0 rounded p-0.5 text-recall-textMuted opacity-0 transition hover:text-recall-text group-hover:opacity-100"
              >
                <SplitIcon size={11} />
              </button>
            )}
            {canEditContent && (
              <button
                onClick={() => {
                  setDraft(content);
                  setIsEditingContent(true);
                }}
                title={t.meeting_export_edit}
                className="flex-shrink-0 rounded p-0.5 text-recall-textMuted opacity-0 transition hover:text-recall-text group-hover:opacity-100"
              >
                <PencilIcon size={11} />
              </button>
            )}
          </p>
        )}
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

function statusBadge(t: any, status: MeetingStatus) {
  switch (status) {
    case "created":
    case "processing":
      return { label: t.meeting_status_analyzing, className: "bg-recall-accent/10 text-recall-accent" };
    case "completed":
      return { label: t.status_done, className: "bg-emerald-500/10 text-emerald-400" };
    case "failed":
      return { label: t.worktree_status_failed, className: "bg-recall-danger/10 text-recall-danger" };
    case "recording":
      return { label: t.voice_status_recording, className: "bg-recall-danger/10 text-recall-danger" };
    case "paused":
      return { label: t.voice_status_paused, className: "bg-recall-textMuted/10 text-recall-textMuted" };
    default:
      return { label: status, className: "bg-recall-textMuted/10 text-recall-textMuted" };
  }
}

function liveStatusLabel(t: any, status: LiveMeetingStatus): string {
  switch (status) {
    case "connecting":
      return t.meeting_live_connecting;
    case "recording":
      return t.voice_status_recording;
    case "paused":
      return t.voice_status_paused;
    case "reconnecting":
      return t.meeting_live_reconnecting;
    case "ending":
      return t.meeting_live_ending;
    default:
      return "";
  }
}

function UploadModal({
  isUploading,
  onClose,
  onUpload,
  t,
}: {
  isUploading: boolean;
  onClose: () => void;
  onUpload: (file: File, title: string) => void;
  t: any;
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
        <h3 className="mb-4 text-lg font-bold">{t.meeting_upload_modal_title}</h3>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-semibold text-recall-textMuted">{t.meeting_upload_title_label}</label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t.meeting_upload_title_placeholder}
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-sm text-recall-text outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-semibold text-recall-textMuted">
              {t.meeting_upload_file_label}
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
              {t.task_cancel}
            </button>
            <button
              type="submit"
              disabled={isUploading || !title.trim() || !file}
              className="rounded-lg bg-recall-accent px-3.5 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
            >
              {isUploading ? t.meeting_upload_uploading : t.meeting_upload_btn}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface MeetingsPanelProps {
  workspaceId: string;
  currentUserId: string;
  avatarUrlByName: Record<string, string | null>;
  liveStatus: LiveMeetingStatus;
  liveMeeting: Meeting | null;
  liveSegments: LiveSegment[];
  livePartial: { confirmed: string; tentative: string };
  liveContradictionAlerts: ContradictionAlert[];
  onClearContradictionAlert: (contradictionId: string) => void;
  liveAudioQualityAlerts: AudioQualityAlert[];
  onClearAudioQualityAlert: (alertId: string) => void;
  agendaReminder: AgendaReminderPopup | null;
  onClearAgendaReminder: () => void;
  liveError: string | null;
  joinableMeeting: Meeting | null;
  isViewer: boolean;
  onStartLive: (
    title: string,
    relatedRoomId?: string,
    attendeeIds?: string[],
    location?: string,
    recordingMode?: RecordingMode,
    categoryId?: string
  ) => void;
  onJoinLive: (meetingId: string) => void;
  onPauseLive: () => void;
  onResumeLive: () => void;
  onStopLive: () => void;
  onLeaveLive: () => void;
  onResetLive: () => void;
  onMapLiveSpeakers: (mapping: Record<string, string>) => void;
  onEditLiveSegment: (segmentId: string, content: string) => Promise<boolean>;
  onRenameLive: (title: string) => void;
  // 홈 화면 "최근 회의록"에서 특정 회의를 클릭해서 들어왔을 때, 그 회의를 바로 선택해서 보여주기 위한 값 -
  // 소비하고 나면 상위(App)에서 null로 리셋해줘야 뒤로 갔다 다시 들어와도 강제로 재선택되지 않는다.
  initialMeetingId?: string | null;
  onInitialMeetingIdConsumed?: () => void;
  // 결정 근거 팝업의 "원본 회의로 이동"에서 세그먼트 id까지 같이 넘어온 경우, 스크립트 탭에서
  // 그 발언까지 스크롤 + 하이라이트해준다.
  initialSegmentId?: string | null;
  onInitialSegmentIdConsumed?: () => void;
  onOpenDecision: (decisionId: string) => void;
  onTaskApproved: () => void;
  t: any;
}

function EditableMeetingTitle({ title, onRename, t }: { title: string; onRename: (title: string) => void; t: any }) {
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
      title={t.meeting_title_edit_tooltip}
      className="group flex items-center gap-1.5 text-left"
    >
      <span className="text-base font-medium text-recall-text">{title}</span>
      <PencilIcon size={12} className="flex-shrink-0 text-recall-textMuted opacity-0 group-hover:opacity-70" />
    </button>
  );
}

function EditableFullSummary({
  text,
  isEditing,
  onSave,
  t,
}: {
  text: string;
  isEditing: boolean;
  onSave: (text: string) => void;
  t: any;
}) {
  const [draft, setDraft] = useState(text);

  useEffect(() => {
    setDraft(text);
  }, [text, isEditing]);

  if (isEditing) {
    return (
      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          const trimmed = draft.trim();
          if (trimmed !== text) onSave(trimmed);
        }}
        rows={10}
        placeholder={t.meeting_full_summary_empty}
        className="w-full rounded-xl border border-recall-border bg-recall-bgMain px-3 py-2 text-xs leading-relaxed text-recall-text outline-none focus:border-recall-accent"
      />
    );
  }

  return (
    <div className="p-3.5 rounded-xl bg-white/5 border border-recall-border/30">
      <p className="whitespace-pre-line text-xs leading-relaxed text-recall-textMuted">
        {text || t.meeting_full_summary_empty}
      </p>
    </div>
  );
}

function DecisionItem({
  decision,
  isEditing,
  onSave,
  t,
}: {
  decision: Decision;
  isEditing: boolean;
  onSave: (input: { title: string; decisionText: string; reason: string | null }) => Promise<boolean>;
  t: any;
}) {
  const [title, setTitle] = useState(decision.title);
  const [decisionText, setDecisionText] = useState(decision.decision_text);
  const [reason, setReason] = useState(decision.reason || "");

  useEffect(() => {
    setTitle(decision.title);
    setDecisionText(decision.decision_text);
    setReason(decision.reason || "");
  }, [decision.id, decision.title, decision.decision_text, decision.reason, isEditing]);

  function commit() {
    const trimmedTitle = title.trim();
    const trimmedText = decisionText.trim();
    // [수정 - 리뷰 반영] 이유를 지워서 빈 문자열로 만들면 여기서 undefined가 되는데,
    // JSON.stringify는 undefined인 키를 아예 빼버려서 서버(Pydantic exclude_unset)가
    // "이유는 안 건드림"으로 해석해 기존 값이 그대로 남아있었다 - null로 명시해서 보낸다.
    const trimmedReason = reason.trim() || null;
    if (!trimmedTitle || !trimmedText) return;
    if (
      trimmedTitle === decision.title &&
      trimmedText === decision.decision_text &&
      trimmedReason === (decision.reason || null)
    ) {
      return;
    }
    onSave({ title: trimmedTitle, decisionText: trimmedText, reason: trimmedReason });
  }

  if (isEditing) {
    return (
      <li className="space-y-1.5 rounded-lg bg-white/5 p-2">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={commit}
          placeholder={t.meeting_decision_title_placeholder}
          className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-xs font-bold text-recall-text outline-none focus:border-recall-accent"
        />
        <textarea
          value={decisionText}
          onChange={(e) => setDecisionText(e.target.value)}
          onBlur={commit}
          rows={2}
          placeholder={t.meeting_decision_text_placeholder}
          className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-xs text-recall-text outline-none focus:border-recall-accent"
        />
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          onBlur={commit}
          placeholder={t.meeting_decision_reason_placeholder}
          className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-xs text-recall-textMuted outline-none focus:border-recall-accent"
        />
      </li>
    );
  }

  return (
    <li className="flex gap-2 text-xs text-recall-text p-2 rounded-lg bg-white/5">
      <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-accent" />
      <span className="flex-1">
        <span className="font-bold">{decision.title}</span>
        <span className="text-recall-textMuted"> — {decision.decision_text}</span>
      </span>
    </li>
  );
}

function EditableShortSummaryField({
  text,
  onSave,
  t,
}: {
  text: string;
  onSave: (text: string) => void;
  t: any;
}) {
  const [draft, setDraft] = useState(text);

  useEffect(() => {
    setDraft(text);
  }, [text]);

  return (
    <input
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const trimmed = draft.trim();
        if (trimmed !== text) onSave(trimmed);
      }}
      placeholder={t.meeting_short_summary_label}
      className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-sm font-bold text-recall-text outline-none focus:border-recall-accent"
    />
  );
}

function EditableTitleField({
  title,
  onSave,
  t,
}: {
  title: string;
  onSave: (title: string) => void;
  t: any;
}) {
  const [draft, setDraft] = useState(title);

  useEffect(() => {
    setDraft(title);
  }, [title]);

  return (
    <input
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const trimmed = draft.trim();
        if (trimmed && trimmed !== title) onSave(trimmed);
      }}
      className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-sm font-bold text-recall-text outline-none focus:border-recall-accent"
    />
  );
}

function EditableLocationField({
  location,
  onSave,
  t,
}: {
  location: string;
  onSave: (location: string) => void;
  t: any;
}) {
  const [draft, setDraft] = useState(location);

  useEffect(() => {
    setDraft(location);
  }, [location]);

  return (
    <input
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const trimmed = draft.trim();
        if (trimmed !== location) onSave(trimmed);
      }}
      placeholder={t.meeting_minutes_datetime_unset}
      className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-xs text-recall-text outline-none focus:border-recall-accent"
    />
  );
}

function AddDecisionForm({
  onAdd,
  t,
}: {
  onAdd: (input: { title: string; decisionText: string; reason?: string }) => Promise<boolean>;
  t: any;
}) {
  const [isAdding, setIsAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [decisionText, setDecisionText] = useState("");
  const [reason, setReason] = useState("");

  if (!isAdding) {
    return (
      <button
        onClick={() => setIsAdding(true)}
        className="flex items-center gap-1 rounded-lg border border-dashed border-recall-border px-2 py-1 text-[11px] text-recall-textMuted transition hover:text-recall-text hover:border-recall-accent"
      >
        <PlusIcon size={11} />
        {t.meeting_decision_add_btn}
      </button>
    );
  }

  return (
    <div className="space-y-1.5 rounded-lg bg-white/5 p-2">
      <input
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={t.meeting_decision_title_placeholder}
        className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-xs font-bold text-recall-text outline-none focus:border-recall-accent"
      />
      <textarea
        value={decisionText}
        onChange={(e) => setDecisionText(e.target.value)}
        rows={2}
        placeholder={t.meeting_decision_text_placeholder}
        className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-xs text-recall-text outline-none focus:border-recall-accent"
      />
      <input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder={t.meeting_decision_reason_placeholder}
        className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-2 py-1 text-xs text-recall-textMuted outline-none focus:border-recall-accent"
      />
      <div className="flex justify-end gap-2">
        <button
          onClick={() => {
            setIsAdding(false);
            setTitle("");
            setDecisionText("");
            setReason("");
          }}
          className="rounded-lg border border-recall-border px-3 py-1 text-[11px] text-recall-textMuted hover:bg-white/5"
        >
          {t.task_cancel}
        </button>
        <button
          onClick={async () => {
            if (!title.trim() || !decisionText.trim()) return;
            const ok = await onAdd({
              title: title.trim(),
              decisionText: decisionText.trim(),
              reason: reason.trim() || undefined,
            });
            if (ok) {
              setIsAdding(false);
              setTitle("");
              setDecisionText("");
              setReason("");
            }
          }}
          className="rounded-lg bg-recall-accent px-3 py-1 text-[11px] font-medium text-white hover:opacity-90"
        >
          {t.task_save}
        </button>
      </div>
    </div>
  );
}

function judgmentCaseLabel(t: any, judgmentCase: string): string {
  const map: Record<string, string> = {
    reasoned_change: t.meeting_live_alert_reasoned,
    unreasoned_change: t.meeting_live_alert_unreasoned,
    decision_reminder: t.meeting_live_alert_reminder,
  };
  return map[judgmentCase] ?? judgmentCase;
}

// 결정 변경 감지 카드(Case2 근거있는 변경 / Case3 근거없는 변경)를 한눈에 구분할 수 있도록
// 아이콘·타이틀·색을 판단 케이스별로 다르게 준다. Case3(근거 없음)이 제일 눈에 띄어야 한다.
function decisionCaseDisplay(t: any, judgmentCase: "reasoned_change" | "unreasoned_change") {
  if (judgmentCase === "unreasoned_change") {
    return {
      Icon: WarningIcon,
      title: t.meeting_decision_case_unreasoned_title,
      colorClass: "text-recall-danger",
      borderClass: "border-recall-danger/30 bg-recall-danger/5",
    };
  }
  return {
    Icon: CheckIcon,
    title: t.meeting_decision_case_reasoned_title,
    colorClass: "text-emerald-400",
    borderClass: "border-emerald-500/30 bg-emerald-500/5",
  };
}

function actionLabel(t: any, action: string): string {
  const map: Record<string, string> = {
    change_acknowledged: t.contradiction_apply,
    keep_reference: t.contradiction_keep,
  };
  return map[action] ?? action;
}

function LiveContradictionToast({
  alert,
  total,
  onResolve,
  onDismiss,
  onViewReference,
  onViewDecision,
  onEditSegment,
  t,
}: {
  alert: ContradictionAlert;
  total: number;
  onResolve: (contradictionId: string, resolutionType: ContradictionResolutionType) => void;
  onDismiss: (contradictionId: string) => void;
  onViewReference?: () => void;
  onViewDecision?: (decisionId: string) => void;
  onEditSegment?: (segmentId: string, content: string) => Promise<boolean>;
  t: any;
}) {
  const isDecision = alert.source === "decision";
  const isReminder = alert.judgmentCase === "decision_reminder";
  // actions가 안 오면(문서 기반, 또는 아직 안 붙은 구버전 응답) 기본 두 액션을 보여준다 -
  // 단, 리마인더(Case0)는 해결 대상이 아니라 애초에 액션이 없다.
  const actions = isReminder
    ? []
    : alert.actions ?? (["keep_reference", "change_acknowledged"] as ContradictionAlertAction[]);

  // 리마인더는 해결할 때까지 기다릴 필요가 없으니, 확인 안 해도 몇 초 뒤 자동으로 큐에서 빠진다
  useEffect(() => {
    if (!isReminder) return;
    const timer = setTimeout(() => onDismiss(alert.contradiction_id), 6000);
    return () => clearTimeout(timer);
  }, [isReminder, alert.contradiction_id]);

  // STT 오인식(예: "9월"을 "구월"로 인식)으로 뜬 모순은, 무시하기보다 원본 발화를 직접
  // 고쳐서 근본 원인을 없애는 게 더 유용하다 - 세그먼트가 있을 때만 이 옵션을 보여준다.
  const canEditSegment = !!onEditSegment && !!alert.meetingSegmentId;
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(alert.statement_text);
  const [isSaving, setIsSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  async function handleSaveEdit() {
    if (!onEditSegment || !alert.meetingSegmentId) return;
    const trimmed = draft.trim();
    if (!trimmed) return;

    setIsSaving(true);
    setEditError(null);
    const ok = await onEditSegment(alert.meetingSegmentId, trimmed);
    setIsSaving(false);

    if (ok) {
      onDismiss(alert.contradiction_id);
    } else {
      setEditError(t.meeting_live_alert_edit_failed);
    }
  }

  if (isEditing) {
    return (
      <div
        className={`mb-2 rounded-xl border p-3 text-xs ${
          isDecision ? "border-purple-500/30 bg-purple-500/5" : "border-recall-accent/30 bg-recall-accent/5"
        }`}
      >
        <p className="mb-1.5 font-bold text-recall-text">{t.meeting_live_alert_edit_title}</p>
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          className="mb-2 w-full rounded-lg border border-recall-border bg-recall-bgMain px-2.5 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
        />
        {editError && <p className="mb-2 text-[11px] text-recall-danger">{editError}</p>}
        <div className="flex gap-1.5">
          <button
            onClick={() => {
              setIsEditing(false);
              setDraft(alert.statement_text);
              setEditError(null);
            }}
            disabled={isSaving}
            className="flex-1 rounded border border-recall-border px-2 py-1 text-[11px] text-recall-textMuted hover:bg-white/5 disabled:opacity-50"
          >
            {t.task_cancel}
          </button>
          <button
            onClick={handleSaveEdit}
            disabled={isSaving || !draft.trim()}
            className="flex-1 rounded bg-recall-accent px-2 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {isSaving ? t.meeting_export_saving : t.task_save}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`mb-2 rounded-xl border p-3 text-xs ${
        isDecision
          ? "border-purple-500/30 bg-purple-500/5"
          : "border-recall-accent/30 bg-recall-accent/5"
      }`}
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span
          className={`flex items-center gap-1.5 font-bold ${
            isDecision ? "text-purple-400" : "text-recall-accent"
          }`}
        >
          {isDecision && <RepeatIcon size={13} />}
          {isReminder
            ? t.meeting_live_alert_reminder_title
            : isDecision
            ? t.meeting_live_alert_decision_title
            : t.contradiction_title}
          {alert.judgmentCase && (
            <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold">
              {judgmentCaseLabel(t, alert.judgmentCase)}
            </span>
          )}
          {total > 1 && (
            <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold">
              {t.meeting_live_alert_count(total)}
            </span>
          )}
        </span>
        <button
          onClick={() => onDismiss(alert.contradiction_id)}
          className="text-recall-textMuted hover:text-recall-text"
          aria-label={t.btn_close}
        >
          <CloseIcon size={13} />
        </button>
      </div>

      <p className="mb-1.5 text-recall-text">{alert.displayMessage || alert.reason || alert.statement_text}</p>

      {alert.referenceSourceName &&
        (() => {
          // 근거가 결정사항이면 결정 미리보기로, 문서면 문서 미리보기로 - 문서 참조든
          // 결정 참조든 항상 "그곳으로 이동"할 수 있는 링크가 뜨게 통일한다.
          const onClick =
            alert.source === "decision"
              ? alert.decisionId && onViewDecision
                ? () => onViewDecision(alert.decisionId!)
                : undefined
              : onViewReference;

          return onClick ? (
            <button
              type="button"
              onClick={onClick}
              className="mb-2 text-[11px] text-recall-accent underline hover:opacity-80"
            >
              {t.agenda_reminder_reason_label}: {alert.referenceSourceName}
            </button>
          ) : (
            <p className="mb-2 text-[11px] text-recall-textMuted">
              {t.agenda_reminder_reason_label}: {alert.referenceSourceName}
            </p>
          );
        })()}

      <div className="flex gap-1.5">
        {isReminder ? (
          <>
            {alert.decisionId && onViewDecision && (
              <button
                onClick={() => onViewDecision(alert.decisionId!)}
                className="flex-1 rounded border border-recall-border px-2 py-1 text-[11px] text-recall-text hover:bg-white/5"
              >
                {t.meeting_live_alert_reminder_view_btn}
              </button>
            )}
            <button
              onClick={() => onDismiss(alert.contradiction_id)}
              className="flex-1 rounded bg-recall-accent px-2 py-1 text-[11px] font-medium text-white hover:opacity-90"
            >
              {t.meeting_live_alert_reminder_ack_btn}
            </button>
          </>
        ) : (
          <>
            {canEditSegment && (
              <button
                onClick={() => setIsEditing(true)}
                className="flex-1 rounded border border-recall-border px-2 py-1 text-[11px] text-recall-textMuted hover:bg-white/5"
              >
                {t.meeting_live_alert_edit_btn}
              </button>
            )}
            {actions.map((action) => (
              <button
                key={action}
                onClick={async () => {
                  if (action === "change_acknowledged") {
                    const ok = await showConfirm(t.contradiction_apply_confirm, t.contradiction_apply, t.task_cancel);
                    if (!ok) return;
                  }
                  onResolve(alert.contradiction_id, action);
                }}
                className={`flex-1 rounded px-2 py-1 text-[11px] font-medium ${
                  action === "change_acknowledged"
                    ? "bg-recall-accent text-white hover:opacity-90"
                    : "border border-recall-border text-recall-text hover:bg-white/5"
                }`}
              >
                {actionLabel(t, action)}
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// 결정 리마인더 - 예전엔 회의 시작 시 화면을 다 가리는 블로킹 모달로 떴지만, 모순/결정변경
// 감지와 같은 큐에 합쳐서 한 번에 하나씩 non-blocking 배너로 보여준다.
function LiveAgendaCard({
  item,
  position,
  total,
  onPrev,
  onNext,
  t,
}: {
  item: AgendaReminderItem;
  position: number;
  total: number;
  onPrev?: () => void;
  onNext: () => void;
  t: any;
}) {
  return (
    <div className="mb-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-bold text-amber-400">
          <WarningIcon size={13} />
          {t.agenda_reminder_title}
          {total > 1 && (
            <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold">
              {position}/{total}
            </span>
          )}
        </span>
      </div>

      <p className="mb-1 text-sm font-bold text-recall-text">{item.title}</p>
      <p className="mb-1.5 text-recall-text">{item.decision_text}</p>
      {item.reason && (
        <p className="mb-2 text-[11px] text-recall-textMuted">
          {t.agenda_reminder_reason_label}: {item.reason}
        </p>
      )}

      <div className="flex gap-1.5">
        {onPrev && (
          <button
            onClick={onPrev}
            className="rounded border border-amber-500/30 px-2 py-1 text-[11px] font-medium text-amber-400 hover:bg-amber-500/10"
          >
            {t.meeting_live_alert_prev_btn}
          </button>
        )}
        <button
          onClick={onNext}
          className="flex-1 rounded bg-recall-accent px-2 py-1 text-[11px] font-medium text-white hover:opacity-90"
        >
          {t.meeting_live_alert_next_btn}
        </button>
      </div>
    </div>
  );
}

// STT 오디오 품질 경고 - 회의를 막지 않는 단순 알림. level이 error(무음/마이크 미선택 등)면
// 눈에 더 띄게 강조한다. message는 서버가 "무엇을 하면 되는지"까지 포함해서 내려주므로 그대로 노출.
function AudioQualityToast({
  alert,
  onDismiss,
  t,
}: {
  alert: AudioQualityAlert;
  onDismiss: (alertId: string) => void;
  t: any;
}) {
  const isError = alert.level === "error";

  return (
    <div
      className={`mb-2 flex items-start gap-2 rounded-xl border p-3 text-xs ${
        isError
          ? "border-recall-danger/40 bg-recall-danger/10"
          : "border-amber-500/30 bg-amber-500/5"
      }`}
    >
      <WarningIcon size={14} className={`mt-0.5 flex-shrink-0 ${isError ? "text-recall-danger" : "text-amber-400"}`} />
      <p className={`flex-1 leading-relaxed ${isError ? "text-recall-danger font-medium" : "text-recall-text"}`}>
        {alert.message}
      </p>
      <button
        onClick={() => onDismiss(alert.id)}
        className="flex-shrink-0 text-recall-textMuted hover:text-recall-text"
        aria-label={t.btn_close}
      >
        <CloseIcon size={13} />
      </button>
    </div>
  );
}

function UnmappedSpeakerChips({
  labels,
  onAssign,
  t,
}: {
  labels: string[];
  onAssign: (mapping: Record<string, string>) => void;
  t: any;
}) {
  if (labels.length === 0) return null;

  function handleClick(label: string) {
    const name = window.prompt(t.meeting_speaker_name_prompt(label), "");
    if (!name || !name.trim()) return;
    onAssign({ [label]: name.trim() });
  }

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-recall-textMuted">{t.meeting_speaker_assign_label}</span>
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

function MeetingExportsList({ workspaceId, t }: { workspaceId: string; t: any }) {
  const [exports, setExports] = useState<MeetingExportRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    getMeetingExportsApi(workspaceId).then((res) => {
      if (cancelled) return;
      if (res.status === "success") setExports(res.exports);
      setIsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  async function handleDownload(item: MeetingExportRecord) {
    setDownloadingId(item.export_id);
    const res = await getDocumentFileApi(workspaceId, item.export_id);
    setDownloadingId(null);

    if (res.status !== "success" || !res.blob) {
      alert(`다운로드 실패: ${res.message}`);
      return;
    }

    const url = URL.createObjectURL(res.blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = item.filename || res.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  const groups: { meetingId: string; meetingTitle: string; items: MeetingExportRecord[] }[] = [];
  const groupIndexByMeetingId = new Map<string, number>();
  for (const item of exports) {
    let idx = groupIndexByMeetingId.get(item.meeting_id);
    if (idx === undefined) {
      idx = groups.length;
      groupIndexByMeetingId.set(item.meeting_id, idx);
      groups.push({ meetingId: item.meeting_id, meetingTitle: item.meeting_title, items: [] });
    }
    groups[idx].items.push(item);
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
      {isLoading ? (
        <p className="py-6 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
      ) : groups.length === 0 ? (
        <p className="py-6 text-center text-xs text-recall-textMuted">{t.meeting_exports_empty}</p>
      ) : (
        <div className="space-y-4">
          {groups.map((group) => (
            <div key={group.meetingId} className="rounded-2xl border border-recall-border bg-white/5 p-3.5">
              <p className="mb-2 text-sm font-bold text-recall-text">{group.meetingTitle}</p>
              <div className="space-y-1.5">
                {group.items.map((item) => (
                  <div
                    key={item.export_id}
                    className="flex items-center justify-between gap-2 rounded-xl border border-recall-border/60 bg-recall-bgSoft/40 px-3 py-2"
                  >
                    <div className="flex min-w-0 items-center gap-1.5">
                      <DocumentIcon size={13} className="flex-shrink-0 text-recall-textMuted" />
                      <div className="min-w-0">
                        <p className="truncate text-xs font-semibold text-recall-text">{item.filename}</p>
                        <p className="text-[11px] text-recall-textMuted">{formatDate(item.created_at)}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDownload(item)}
                      disabled={downloadingId === item.export_id}
                      className="flex flex-shrink-0 items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5 disabled:opacity-50"
                    >
                      <DownloadIcon size={12} />
                      {downloadingId === item.export_id ? t.meeting_exports_downloading : t.meeting_exports_download}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function MeetingsPanel({
  workspaceId,
  currentUserId,
  avatarUrlByName,
  liveStatus,
  liveMeeting,
  liveSegments,
  livePartial,
  liveContradictionAlerts,
  onClearContradictionAlert,
  liveAudioQualityAlerts,
  onClearAudioQualityAlert,
  agendaReminder,
  onClearAgendaReminder,
  liveError,
  joinableMeeting,
  isViewer,
  onStartLive,
  onJoinLive,
  onPauseLive,
  onResumeLive,
  onStopLive,
  onLeaveLive,
  onResetLive,
  onMapLiveSpeakers,
  onEditLiveSegment,
  onRenameLive,
  initialMeetingId,
  onInitialMeetingIdConsumed,
  initialSegmentId,
  onInitialSegmentIdConsumed,
  onOpenDecision,
  onTaskApproved,
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
    addDecision,
    updateDecision,
    attendees,
    suggestedTasks,
    approveSuggestedTask,
    rejectSuggestedTask,
    reloadAttendees,
    isDetailLoading,
    isUploading,
    uploadAudio,
    removeMeeting,
    renameMeeting,
    updateMeetingLocation,
    mapSpeakerNames,
    assignSegmentSpeaker,
    updateSegmentContent,
    splitSegment,
    updateFullSummary,
    updateShortSummary,
    reload,
    upsertMeeting,
  } = useRealMeetings(workspaceId);

  // 홈 화면 "최근 회의록"에서 특정 회의를 클릭해서 들어온 경우, 그 회의를 바로 선택해서 보여준다.
  useEffect(() => {
    if (!initialMeetingId) return;
    setSelectedMeetingId(initialMeetingId);
    setTopTab("meetings");
    onInitialMeetingIdConsumed?.();
  }, [initialMeetingId]);

  const [splitTargetSegmentId, setSplitTargetSegmentId] = useState<string | null>(null);

  // 스크립트 전체 수정 - 줄마다 수정 버튼을 따로 누르지 않고, 한 번에 전부 편집 가능한 상태로 켰다가
  // 바뀐 줄만 모아서 한 번에 저장한다. 백엔드는 여전히 줄 단위 PATCH라 프론트에서만 모아서 처리.
  const [bulkEditDrafts, setBulkEditDrafts] = useState<Record<string, string> | null>(null);
  const [isBulkSaving, setIsBulkSaving] = useState(false);

  useEffect(() => {
    setBulkEditDrafts(null);
  }, [selectedMeetingId]);

  function startBulkEdit() {
    const drafts: Record<string, string> = {};
    segments.forEach((s) => {
      drafts[s.id] = s.content;
    });
    setBulkEditDrafts(drafts);
  }

  function cancelBulkEdit() {
    setBulkEditDrafts(null);
  }

  async function saveBulkEdit() {
    if (!bulkEditDrafts) return;
    const changed = segments.filter((s) => {
      const draft = bulkEditDrafts[s.id]?.trim();
      return draft !== undefined && draft.length > 0 && draft !== s.content;
    });
    if (changed.length === 0) {
      setBulkEditDrafts(null);
      return;
    }
    setIsBulkSaving(true);
    await Promise.all(changed.map((s) => updateSegmentContent(s.id, bulkEditDrafts[s.id].trim())));
    setIsBulkSaving(false);
    setBulkEditDrafts(null);
  }

  const [registeredSpeakerNames, setRegisteredSpeakerNames] = useState<string[]>([]);
  useEffect(() => {
    let cancelled = false;
    getVoiceProfileListApi().then((res) => {
      if (!cancelled && res.status === "success") setRegisteredSpeakerNames(res.names);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const {
    contradictions: workspaceContradictions,
    isLoading: isContradictionsLoading,
    statusFilter: contradictionStatusFilter,
    setStatusFilter: setContradictionStatusFilter,
    resolve,
    dismiss,
    reopen,
    update: updateContradiction,
    refresh: refreshContradictions,
    pendingSummaryFor,
    changeSummary,
    isChangeSummaryLoading,
    closeChangeSummary,
  } = useContradictions(workspaceId);

  const { reminders: allDecisionReminders, markRead: markReminderRead } = useDecisionReminders(workspaceId);
  const meetingSegmentIds = new Set(
    [...(segments || []).map((s) => s.id), ...(liveSegments || []).map((s) => s.id)].filter(
      (id): id is string => !!id
    )
  );
  const meetingReminders = allDecisionReminders.filter(
    (n) => n.ref_type === "meeting_segment" && n.ref_id && meetingSegmentIds.has(n.ref_id)
  );

  async function handleLiveAlertResolve(contradictionId: string, resolutionType: ContradictionResolutionType) {
    await resolve(contradictionId, resolutionType);
    onClearContradictionAlert(contradictionId);
  }

  function handleLiveAlertDismiss(contradictionId: string) {
    dismiss(contradictionId);
    onClearContradictionAlert(contradictionId);
  }

  // 결정 리마인더 + 모순/결정변경 감지를 하나의 큐로 합쳐서 한 번에 하나씩만 보여준다 -
  // 예전엔 리마인더는 회의 시작 시 블로킹 모달로, 모순은 스크립트 위에 각각 배너로 쌓여서
  // 여러 개가 한꺼번에 뜨면 화면이 복잡해 보였다.
  // [수정 - 리뷰 반영] 예전엔 "다음"을 누른 안건을 seen Set에 넣어 큐에서 영영 빼버려서,
  // "이전" 버튼을 만들 수가 없었다(빠진 항목은 다시 못 불러옴). items 안에서의 위치를
  // 가리키는 인덱스로 바꿔서, 안건들 사이는 앞뒤로 자유롭게 오갈 수 있게 한다.
  const [agendaIndex, setAgendaIndex] = useState(0);
  useEffect(() => {
    if (agendaReminder) setAgendaIndex(0);
  }, [agendaReminder]);

  const currentAgendaItem =
    agendaReminder && agendaIndex < agendaReminder.items.length ? agendaReminder.items[agendaIndex] : null;

  const liveAlertQueue: LiveAlertQueueItem[] = [
    ...(currentAgendaItem ? [{ kind: "agenda" as const, id: `agenda-${currentAgendaItem.id}`, item: currentAgendaItem }] : []),
    ...liveContradictionAlerts.map((alert) => ({
      kind: "contradiction" as const,
      id: alert.contradiction_id,
      alert,
    })),
  ];
  const currentLiveAlert = liveAlertQueue[0] ?? null;

  function handleAgendaItemNext() {
    if (!agendaReminder) return;
    if (agendaIndex + 1 < agendaReminder.items.length) {
      setAgendaIndex(agendaIndex + 1);
    } else {
      onClearAgendaReminder();
    }
  }

  function handleAgendaItemPrev() {
    setAgendaIndex((i) => Math.max(0, i - 1));
  }

  const prevAlertCountRef = useRef(liveContradictionAlerts.length);
  useEffect(() => {
    if (liveContradictionAlerts.length > prevAlertCountRef.current) {
      refreshContradictions();
    }
    prevAlertCountRef.current = liveContradictionAlerts.length;
  }, [liveContradictionAlerts.length]);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("summary");
  // 회의록 내보내기의 "수정" 버튼처럼, 하나의 토글로 요약/회의록 탭을 한 번에 편집 모드로
  // 전환한다 - 탭을 옮겨 다녀도 편집 모드가 유지된다 (같은 컴포넌트 안의 state라 탭 전환에
  // 안 날아감). 스크립트 탭은 원래부터 항상 줄 단위로 바로 수정 가능해서 이 토글과 무관하다.
  const [isMeetingEditMode, setIsMeetingEditMode] = useState(false);
  const [isMeetingListOpen, setIsMeetingListOpen] = useState(true);
  const [isContradictionListOpen, setIsContradictionListOpen] = useState(true);
  const [expandedContradictionIds, setExpandedContradictionIds] = useState<Set<string>>(new Set());
  const [editingContradictionId, setEditingContradictionId] = useState<string | null>(null);
  const [previewDoc, setPreviewDoc] = useState<{ id: string; name: string } | null>(null);
  const [showAttendeesModal, setShowAttendeesModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showStartModal, setShowStartModal] = useState(false);
  const [topTab, setTopTab] = useState<"meetings" | "exports">("meetings");
  const categoriesState = useCategories(workspaceId);
  const categoryById = new Map(categoriesState.categories.map((c) => [c.id, c]));
  const [collapsedCategoryIds, setCollapsedCategoryIds] = useState<Set<string>>(new Set());
  const [startCategoryId, setStartCategoryId] = useState<string | null>(null);
  const [isAddingCategory, setIsAddingCategory] = useState(false);
  const [newCategoryDraftName, setNewCategoryDraftName] = useState("");

  async function handleConfirmAddCategory() {
    const name = newCategoryDraftName.trim();
    if (!name) return;
    await categoriesState.createCategory(name);
    setIsAddingCategory(false);
    setNewCategoryDraftName("");
  }

  // 카테고리 추가 입력창이 열려 있을 때 바깥을 클릭하면 만들지 않고 그냥 접는다
  const addCategoryRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isAddingCategory) return;
    function handleClickOutside(e: MouseEvent) {
      if (addCategoryRef.current && !addCategoryRef.current.contains(e.target as Node)) {
        setIsAddingCategory(false);
        setNewCategoryDraftName("");
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isAddingCategory]);

  const audioPlayerRef = useRef<MeetingAudioPlayerHandle>(null);

  // 결정 근거 팝업의 "원본 회의로 이동"에서 세그먼트 id까지 넘어온 경우 - 그 회의가 선택되고
  // 스크립트(segments)까지 로딩된 다음에야 실제 DOM에 해당 줄이 존재하므로, segments가 그
  // 세그먼트를 포함하게 될 때까지 기다렸다가 스크립트 탭으로 전환 + 스크롤/하이라이트한다.
  const [highlightSegmentId, setHighlightSegmentId] = useState<string | null>(null);
  useEffect(() => {
    if (!initialSegmentId) return;
    if (!segments.some((s) => s.id === initialSegmentId)) return;
    setDetailTab("script");
    setHighlightSegmentId(initialSegmentId);
    onInitialSegmentIdConsumed?.();
  }, [initialSegmentId, segments]);

  useEffect(() => {
    if (!highlightSegmentId) return;
    document.getElementById(`segment-${highlightSegmentId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = setTimeout(() => setHighlightSegmentId(null), 3000);
    return () => clearTimeout(timer);
  }, [highlightSegmentId]);

  // 실시간 회의 스크립트 - 새 발화가 쌓여도 자동으로 안 내려가서, 계속 손으로 스크롤해야
  // 방금 나온 말을 볼 수 있었다. 확정 발화든 진행 중인 부분 인식(partial)이든 바뀔 때마다
  // 맨 아래로 스크롤한다.
  const liveScriptBottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    liveScriptBottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [liveSegments.length, livePartial.confirmed, livePartial.tentative]);

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

  // 회의를 바꿔 볼 때마다 패널을 열지/접을지 다시 정한다 - 진행 중인 회의는 실시간 배너가
  // 이미 알려주고 있으니 접어두고, 다 끝난 회의를 나중에 열어볼 땐 미해결 모순이나 안 읽은
  // 리마인더가 있으면 처음부터 펼쳐서 놓치고 지나가지 않게 한다.
  const autoDecidedMeetingIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedMeetingId || isContradictionsLoading) return;
    if (autoDecidedMeetingIdRef.current === selectedMeetingId) return;
    autoDecidedMeetingIdRef.current = selectedMeetingId;

    if (isViewingLive) {
      setIsContradictionListOpen(false);
    } else {
      const hasUnresolved = contradictions.length > 0 || meetingReminders.some((r) => !r.is_read);
      setIsContradictionListOpen(hasUnresolved);
    }
  }, [selectedMeetingId, isViewingLive, isContradictionsLoading, contradictions.length, meetingReminders]);

  useEffect(() => {
    if (isLiveActive && liveMeeting) {
      setSelectedMeetingId(liveMeeting.id);
    }
  }, [isLiveActive, liveMeeting?.id]);

  useEffect(() => {
    if (liveStatus === "ended") {
      // 서버 목록을 다시 받아오기 전에, 방금 끝난 회의를 "분석 중" 상태로 즉시 반영해서
      // reload()가 실패/지연되더라도 화면이 통째로 비어 보이지 않게 한다.
      if (liveMeeting) {
        upsertMeeting({ ...liveMeeting, status: "processing" });
        setSelectedMeetingId(liveMeeting.id);
      }
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
    return t.meeting_default_title(d.getMonth() + 1, d.getDate());
  }

  function handleStartRecording(categoryId?: string) {
    setStartCategoryId(categoryId ?? null);
    setShowStartModal(true);
  }

  function toggleCategoryCollapsed(categoryId: string) {
    setCollapsedCategoryIds((prev) => {
      const next = new Set(prev);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      return next;
    });
  }

  function renderMeetingCard(m: Meeting, opts: { showCategoryChip: boolean }) {
    const isSelected = m.id === selectedMeetingId;
    const isThisLive = isLiveActive && liveMeeting && m.id === liveMeeting.id;
    const badge = statusBadge(t, m.status);
    const category = m.category_id ? categoryById.get(m.category_id) : null;
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
          <span className="min-w-0 flex-1 truncate text-xs font-bold text-recall-text">{m.title}</span>
          {!isThisLive && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                removeMeeting(m.id);
              }}
              className="hidden flex-shrink-0 text-recall-textMuted hover:text-recall-danger group-hover:inline transition"
              aria-label={t.meeting_delete_aria}
            >
              <TrashIcon size={12} />
            </button>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {isThisLive && <span className="h-1.5 w-1.5 flex-shrink-0 animate-pulse rounded-full bg-recall-danger" />}
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${badge.className}`}>
            {isThisLive ? liveStatusLabel(t, liveStatus) : badge.label}
          </span>
          <span className="text-[11px] text-recall-textMuted">{formatDate(m.created_at)}</span>
          {opts.showCategoryChip && category && !category.is_default && (
            <span className="ml-auto truncate rounded-full border border-recall-accent/30 bg-recall-accent/10 px-2 py-0.5 text-xs font-semibold text-recall-accent">
              {category.name}
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden bg-recall-bgMain">
      <div className="flex gap-0.5 border-b border-recall-border px-3 pt-2 flex-shrink-0">
        <button
          onClick={() => setTopTab("meetings")}
          className={`px-2 pb-2 text-sm transition ${
            topTab === "meetings"
              ? "border-b-2 border-recall-accent font-medium text-recall-accent"
              : "text-recall-textMuted hover:text-recall-text"
          }`}
        >
          {t.meeting_top_tab_meetings}
        </button>
        <button
          onClick={() => setTopTab("exports")}
          className={`px-2 pb-2 text-sm transition ${
            topTab === "exports"
              ? "border-b-2 border-recall-accent font-medium text-recall-accent"
              : "text-recall-textMuted hover:text-recall-text"
          }`}
        >
          {t.meeting_top_tab_exports}
        </button>
      </div>

      {topTab === "exports" ? (
        <MeetingExportsList workspaceId={workspaceId} t={t} />
      ) : (
      <div className="flex flex-1 overflow-hidden">
      {/* 왼쪽 회의 목록 패널 */}
      {!isMeetingListOpen ? (
        <button
          onClick={() => setIsMeetingListOpen(true)}
          title={t.meeting_list_expand}
          className="flex h-full w-8 flex-shrink-0 flex-col items-center justify-center gap-1.5 border-r border-recall-border text-recall-textMuted hover:bg-white/5"
        >
          <ChevronRightIcon size={13} />
          <span style={{ writingMode: "vertical-rl" }} className="text-xs">
            {t.meeting_top_tab_meetings}
          </span>
        </button>
      ) : (
        <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
          {/* 목록 패널 헤더 (타이틀 + 접기 버튼) */}
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-bold uppercase tracking-wider text-recall-textMuted">{t.meeting_list_title}</p>
            <button
              onClick={() => setIsMeetingListOpen(false)}
              title={t.meeting_list_collapse}
              className="flex h-6 w-6 items-center justify-center rounded hover:bg-white/5 transition"
            >
              <ChevronLeftIcon size={13} className="text-recall-textMuted" />
            </button>
          </div>

          {/* 🌟 단일 메인 CTA 버튼: 새 회의 시작 */}
          <div className="mb-3 space-y-2">
            <button
              onClick={() => handleStartRecording()}
              disabled={isLiveActive}
              title={isLiveActive ? t.meeting_already_running : undefined}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-recall-accent py-3 px-4 text-sm font-bold text-white shadow-md shadow-recall-accent/25 hover:opacity-95 active:scale-95 transition-all disabled:cursor-not-allowed disabled:opacity-40"
            >
              <MicIcon size={16} />
              <span>{t.meeting_start_new}</span>
            </button>

            {/* 보조 업로드 버튼 */}
            <button
              onClick={() => setShowUploadModal(true)}
              className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-recall-border bg-recall-bgSoft/60 py-2 text-xs font-semibold text-recall-textMuted hover:bg-white/5 hover:text-recall-text transition"
            >
              <UploadIcon size={13} />
              <span>{t.meeting_upload_audio_btn}</span>
            </button>
          </div>

          {/* 카테고리 추가 - 설정 화면까지 안 가고 회의 페이지에서 바로 만들 수 있게 */}
          <div ref={addCategoryRef}>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[11px] font-bold uppercase tracking-wider text-recall-textMuted">
              {t.meeting_category_label}
            </p>
            {!isAddingCategory && (
              <button
                onClick={() => setIsAddingCategory(true)}
                className="flex items-center gap-1 text-[11px] font-semibold text-recall-accent hover:opacity-80"
              >
                <PlusIcon size={12} />
                {t.meeting_category_add_btn}
              </button>
            )}
          </div>
          {isAddingCategory && (
            <div className="mb-2 flex gap-1.5">
              <input
                autoFocus
                value={newCategoryDraftName}
                onChange={(e) => setNewCategoryDraftName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleConfirmAddCategory();
                  if (e.key === "Escape") setIsAddingCategory(false);
                }}
                placeholder={t.meeting_category_create_placeholder}
                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-2.5 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
              />
              <button
                onClick={handleConfirmAddCategory}
                disabled={!newCategoryDraftName.trim()}
                className="flex-shrink-0 rounded-lg bg-recall-accent px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
              >
                {t.meeting_category_create_confirm}
              </button>
            </div>
          )}
          </div>

          {/* 회의 리스트 영역 - 기본 카테고리는 폴더로 안 묶고 그냥 flat하게 보여주고
              (모든 회의가 다 "기본값" 폴더 하나에 몰려 있는 건 의미가 없으니), 사용자가
              직접 만든 카테고리만 접고 펼 수 있는 폴더로 묶는다 */}
          <div className="flex-1 space-y-1.5 overflow-y-auto custom-scrollbar pr-0.5">
            {isLoading ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.common_loading}</p>
            ) : meetings.length === 0 ? (
              <p className="py-6 text-center text-xs text-recall-textMuted">{t.meeting_none}</p>
            ) : (
              <>
                {meetings
                  .filter((m) => {
                    const cat = m.category_id ? categoryById.get(m.category_id) : null;
                    return !cat || cat.is_default;
                  })
                  .map((m) => renderMeetingCard(m, { showCategoryChip: false }))}

                {categoriesState.categories
                  .filter((cat) => !cat.is_default)
                  .map((cat) => {
                    const catMeetings = meetings.filter((m) => m.category_id === cat.id);
                    const isCollapsed = collapsedCategoryIds.has(cat.id);
                    return (
                      <div key={cat.id}>
                        <div className="group/cat flex items-center gap-1 rounded-lg px-1 py-1.5 hover:bg-white/5">
                          <button
                            onClick={() => toggleCategoryCollapsed(cat.id)}
                            className="flex flex-1 items-center gap-1.5 text-left"
                          >
                            {isCollapsed ? (
                              <ChevronRightIcon size={13} className="flex-shrink-0 text-recall-textMuted" />
                            ) : (
                              <ChevronDownIcon size={13} className="flex-shrink-0 text-recall-textMuted" />
                            )}
                            <span className="truncate text-sm font-bold text-recall-text">{cat.name}</span>
                            <span className="flex-shrink-0 text-xs text-recall-textMuted">{catMeetings.length}</span>
                          </button>
                          <button
                            onClick={() => handleStartRecording(cat.id)}
                            disabled={isLiveActive}
                            title={t.meeting_start_new}
                            className="hidden flex-shrink-0 text-recall-textMuted hover:text-recall-accent group-hover/cat:inline disabled:opacity-40"
                          >
                            <PlusIcon size={14} />
                          </button>
                        </div>
                        {!isCollapsed && (
                          <div className="mt-1 space-y-1.5 pl-1">
                            {catMeetings.length === 0 ? (
                              <p className="px-1.5 py-1 text-[11px] text-recall-textMuted">{t.meeting_none}</p>
                            ) : (
                              catMeetings.map((m) => renderMeetingCard(m, { showCategoryChip: false }))
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
              </>
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
                {isViewer ? (
                  <p className="text-base font-medium text-recall-text">{liveMeeting.title}</p>
                ) : (
                  <EditableMeetingTitle title={liveMeeting.title} onRename={onRenameLive} t={t} />
                )}
                <p className="flex items-center gap-1.5 text-xs text-recall-textMuted mt-0.5">
                  {liveStatus === "recording" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 animate-pulse rounded-full bg-recall-danger" />
                  )}
                  {liveStatusLabel(t, liveStatus)}
                  {isViewer && <span className="text-recall-textMuted/70">· {t.meeting_view_only_badge}</span>}
                </p>
              </div>
              <div className="flex gap-1.5">
                {isViewer ? (
                  (liveStatus === "recording" || liveStatus === "paused") && (
                    <button
                      onClick={onLeaveLive}
                      className="flex items-center gap-1.5 rounded-full border border-recall-border px-3 py-1.5 text-xs font-semibold text-recall-text hover:bg-white/5 transition"
                    >
                      {t.meeting_leave_btn}
                    </button>
                  )
                ) : (
                  <>
                    {liveStatus === "recording" && (
                      <button
                        onClick={onPauseLive}
                        className="flex items-center gap-1.5 rounded-full border border-recall-border px-3 py-1.5 text-xs font-semibold text-recall-text hover:bg-white/5 transition"
                      >
                        <PauseIcon size={13} />
                        {t.meeting_live_pause}
                      </button>
                    )}
                    {liveStatus === "paused" && (
                      <button
                        onClick={onResumeLive}
                        className="flex items-center gap-1.5 rounded-full border border-recall-accent px-3 py-1.5 text-xs font-semibold text-recall-accent hover:bg-recall-accent/10 transition"
                      >
                        <PlayIcon size={13} />
                        {t.meeting_live_resume}
                      </button>
                    )}
                    {(liveStatus === "recording" || liveStatus === "paused") && (
                      <button
                        onClick={onStopLive}
                        className="flex items-center gap-1.5 rounded-full bg-red-600 px-4 py-1.5 text-xs font-bold text-white hover:bg-red-500 transition shadow-md active:scale-95"
                      >
                        <StopIcon size={13} />
                        {t.meeting_live_stop}
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>

            {liveMeeting.recording_mode === "individual" &&
              (liveStatus === "recording" || liveStatus === "paused" || liveStatus === "connecting") && (
                <div className="mb-2 flex items-center gap-2 rounded-xl border border-recall-accent/30 bg-recall-accent/5 px-3 py-2 text-xs text-recall-accent">
                  <HeadphoneIcon size={14} className="flex-shrink-0" />
                  {t.meeting_headphone_required_notice}
                </div>
              )}

            {liveAudioQualityAlerts.length > 0 && (
              <div className="mb-2 max-h-56 flex-shrink-0 overflow-y-auto custom-scrollbar">
                {liveAudioQualityAlerts.map((alert) => (
                  <AudioQualityToast key={alert.id} alert={alert} onDismiss={onClearAudioQualityAlert} t={t} />
                ))}
              </div>
            )}

            {currentLiveAlert && (
              <div className="flex-shrink-0">
                {currentLiveAlert.kind === "agenda" ? (
                  <LiveAgendaCard
                    item={currentLiveAlert.item}
                    position={agendaIndex + 1}
                    total={agendaReminder?.items.length ?? 1}
                    onPrev={agendaIndex > 0 ? handleAgendaItemPrev : undefined}
                    onNext={handleAgendaItemNext}
                    t={t}
                  />
                ) : (
                  <LiveContradictionToast
                    alert={currentLiveAlert.alert}
                    total={liveAlertQueue.length}
                    onResolve={handleLiveAlertResolve}
                    onDismiss={handleLiveAlertDismiss}
                    onViewReference={
                      currentLiveAlert.alert.referenceFileId
                        ? () =>
                            setPreviewDoc({
                              id: currentLiveAlert.alert.referenceFileId!,
                              name: currentLiveAlert.alert.referenceSourceName || t.home_review_default_source,
                            })
                        : undefined
                    }
                    onViewDecision={onOpenDecision}
                    onEditSegment={onEditLiveSegment}
                    t={t}
                  />
                )}
              </div>
            )}

            <div className="flex-1 overflow-y-auto rounded-2xl border border-recall-border bg-white/5 p-4 custom-scrollbar">
              {liveStatus === "reconnecting" && (
                <div className="mb-2 flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
                  <div className="h-3.5 w-3.5 flex-shrink-0 animate-spin rounded-full border-2 border-amber-500/30 border-t-amber-400" />
                  {t.meeting_live_reconnect_banner}
                </div>
              )}
              {liveStatus === "connecting" || liveStatus === "ending" ? (
                <div className="flex h-full flex-col items-center justify-center gap-2">
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                  <p className="text-xs text-recall-textMuted">{liveStatusLabel(t, liveStatus)}</p>
                </div>
              ) : liveSegments.length === 0 && !livePartial.confirmed && !livePartial.tentative ? (
                <p className="text-sm text-recall-textMuted">
                  {liveStatus === "paused" ? t.meeting_live_paused_notice : t.meeting_live_waiting_speech}
                </p>
              ) : (
                <div className="space-y-3 text-sm text-recall-textMuted">
                  <UnmappedSpeakerChips
                    labels={uniqueRawSpeakerLabels(liveSegments.map((s) => s.speaker_label))}
                    onAssign={onMapLiveSpeakers}
                    t={t}
                  />
                  {liveSegments.map((s, i) => (
                    <SegmentRow
                      key={i}
                      speakerLabel={s.speaker_label}
                      avatarImageUrl={s.speaker_label ? avatarUrlByName[s.speaker_label] : null}
                      timeMs={s.start_ms}
                      content={s.content}
                      hasContradiction={liveContradictionAlerts.some((a) => a.statement_text === s.content)}
                      t={t}
                    />
                  ))}
                  {(livePartial.confirmed || livePartial.tentative) && (
                    <p className="text-recall-textMuted">
                      <span className="font-medium text-recall-text">{t.meeting_live_self_label}</span> {livePartial.confirmed}
                      <span className="opacity-60">{livePartial.tentative}</span>
                    </p>
                  )}
                  <div ref={liveScriptBottomRef} />
                </div>
              )}
            </div>
          </>
        ) : liveStatus === "error" && !selectedRealMeeting ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3">
            <p className="text-sm text-recall-danger">{liveError || t.meeting_generic_error}</p>
            <button
              onClick={onResetLive}
              className="rounded-xl border border-recall-border px-4 py-2 text-xs font-semibold text-recall-text hover:bg-white/5 transition"
            >
              {t.btn_close}
            </button>
          </div>
        ) : !selectedRealMeeting ? (
          /* 🌟 [개선됨] 선택된 회의가 없을 때: 중복 카드 제거 후 깔끔한 안내 텍스트만 표시 */
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-recall-textMuted text-2xl">
            </div>
            <p className="text-sm font-medium text-recall-textMuted">
              {t.meeting_select_or_start} <span className="text-recall-accent font-semibold">{t.meeting_new_meeting_word}</span>{t.meeting_select_or_start_suffix}
            </p>

            {joinableMeeting && (
              <div className="mt-2 flex flex-col items-center gap-2 rounded-2xl border border-recall-accent/40 bg-recall-accent/5 px-5 py-4">
                <p className="text-sm font-semibold text-recall-text">
                  {joinableMeeting.recording_mode === "individual"
                    ? t.meeting_joinable_notice(joinableMeeting.title)
                    : t.meeting_viewable_notice(joinableMeeting.title)}
                </p>
                <button
                  onClick={() => onJoinLive(joinableMeeting.id)}
                  className="rounded-xl bg-recall-accent px-4 py-2 text-xs font-semibold text-white hover:opacity-90 transition"
                >
                  {joinableMeeting.recording_mode === "individual" ? t.meeting_join_btn : t.meeting_view_live_btn}
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
                  t={t}
                  onRename={(title) => renameMeeting(selectedRealMeeting.id, title)}
                />
                <p className="flex items-center gap-1.5 text-xs text-recall-textMuted mt-0.5">
                  <span>
                    {statusBadge(t, selectedRealMeeting.status).label} · {formatDate(selectedRealMeeting.created_at)}
                    {selectedRealMeeting.duration_ms ? ` · ${formatDuration(selectedRealMeeting.duration_ms)}` : ""}
                  </span>
                  {(() => {
                    const category = selectedRealMeeting.category_id
                      ? categoryById.get(selectedRealMeeting.category_id)
                      : null;
                    return category && !category.is_default ? (
                      <span className="rounded-full border border-recall-accent/30 bg-recall-accent/10 px-2 py-0.5 text-xs font-semibold text-recall-accent">
                        {category.name}
                      </span>
                    ) : null;
                  })()}
                </p>
              </div>
              <div className="flex flex-shrink-0 gap-1.5">
                <button
                  onClick={() => setShowAttendeesModal(true)}
                  className="flex items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5 transition"
                >
                  <PersonIcon size={12} />
                  {t.meeting_attendees_btn}
                </button>
                <button
                  onClick={() => setShowExportModal(true)}
                  className="flex items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5 transition"
                >
                  <DocumentIcon size={12} />
                  {t.meeting_export_title}
                </button>
              </div>
            </div>

            {(selectedRealMeeting.input_type === "audio_upload" ||
              selectedRealMeeting.status === "completed" ||
              selectedRealMeeting.status === "failed") && (
              <div className="mb-3">
                <MeetingAudioPlayer ref={audioPlayerRef} workspaceId={workspaceId} meetingId={selectedRealMeeting.id} t={t} />
              </div>
            )}

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
                <div className="mb-3 flex items-center justify-between gap-2 border-b border-recall-border">
                  <div className="flex gap-2">
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
                  {(detailTab === "summary" || detailTab === "minutes") && (
                    <button
                      onClick={() => setIsMeetingEditMode((v) => !v)}
                      className={`mb-1.5 flex flex-shrink-0 items-center gap-1 rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
                        isMeetingEditMode
                          ? "border-recall-accent bg-recall-accent text-white hover:opacity-90"
                          : "border-recall-border text-recall-textMuted hover:text-recall-text"
                      }`}
                    >
                      {isMeetingEditMode ? (
                        <CheckIcon size={12} />
                      ) : (
                        <PencilIcon size={12} />
                      )}
                      {isMeetingEditMode ? t.meeting_edit_done_btn : t.meeting_edit_btn}
                    </button>
                  )}
                </div>

                <div className="flex-1 overflow-y-auto rounded-2xl border border-recall-border bg-white/5 p-4 custom-scrollbar">
                  {isDetailLoading ? (
                    <p className="text-xs text-recall-textMuted">{t.common_loading}</p>
                  ) : detailTab === "summary" ? (
                    summary?.generation_status === "completed" ? (
                      <div className="space-y-4">
                        {(summary.short_summary || isMeetingEditMode) && (
                          <div className="p-3.5 rounded-xl bg-recall-accent/10 border border-recall-accent/20">
                            <p className="text-xs font-bold text-recall-accent uppercase mb-1">{t.meeting_short_summary_label}</p>
                            {isMeetingEditMode ? (
                              <EditableShortSummaryField
                                text={summary.short_summary || ""}
                                onSave={updateShortSummary}
                                t={t}
                              />
                            ) : (
                              <p className="text-sm font-bold text-recall-text">{summary.short_summary}</p>
                            )}
                          </div>
                        )}
                        <EditableFullSummary
                          text={summary.full_summary || ""}
                          isEditing={isMeetingEditMode}
                          onSave={updateFullSummary}
                          t={t}
                        />
                        <div className="border-t border-recall-border pt-3">
                          <p className="mb-2 text-xs font-bold uppercase tracking-wide text-recall-textMuted">
                            {t.meeting_summary_key_decisions}
                          </p>
                          {decisions.length > 0 && (
                            <ul className="mb-2 space-y-1.5">
                              {decisions.map((d) => (
                                <DecisionItem
                                  key={d.id}
                                  decision={d}
                                  isEditing={isMeetingEditMode}
                                  onSave={(input) => updateDecision(d.id, input)}
                                  t={t}
                                />
                              ))}
                            </ul>
                          )}
                          {isMeetingEditMode && <AddDecisionForm onAdd={addDecision} t={t} />}
                        </div>
                        {suggestedTasks.length > 0 && (
                          <div className="border-t border-recall-border pt-3">
                            <p className="mb-2 text-xs font-bold uppercase tracking-wide text-recall-textMuted">
                              {t.meeting_suggested_tasks_title}
                            </p>
                            <ul className="space-y-1.5">
                              {suggestedTasks.map((task) => (
                                <li
                                  key={task.id}
                                  className="flex items-start justify-between gap-2 rounded-lg bg-white/5 p-2 text-xs text-recall-text"
                                >
                                  <div className="min-w-0">
                                    <p className="font-bold">{task.title}</p>
                                    {task.description && (
                                      <p className="mt-0.5 text-recall-textMuted">{task.description}</p>
                                    )}
                                    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-recall-textMuted">
                                      <span className="flex items-center gap-1">
                                        <PersonIcon size={11} className="flex-shrink-0" />
                                        {task.assignee_label || t.meeting_suggested_task_unassigned}
                                      </span>
                                      {task.due_at && (
                                        <span className="flex items-center gap-1">
                                          <span className="opacity-50">·</span>
                                          {formatDateOnly(task.due_at)}
                                        </span>
                                      )}
                                    </p>
                                  </div>
                                  <div className="flex flex-shrink-0 gap-1.5">
                                    <button
                                      onClick={() => rejectSuggestedTask(task.id)}
                                      title={t.meeting_suggested_task_reject}
                                      aria-label={t.meeting_suggested_task_reject}
                                      className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-recall-border text-recall-textMuted transition hover:border-recall-danger hover:text-recall-danger"
                                    >
                                      <CloseIcon size={12} />
                                    </button>
                                    <button
                                      onClick={async () => {
                                        const ok = await approveSuggestedTask(task.id);
                                        if (ok) onTaskApproved();
                                      }}
                                      title={t.meeting_suggested_task_add}
                                      aria-label={t.meeting_suggested_task_add}
                                      className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-recall-accent text-white transition hover:opacity-90"
                                    >
                                      <CheckIcon size={12} />
                                    </button>
                                  </div>
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
                      return (
                        <div className="space-y-4 text-xs">
                          <div>
                            {isMeetingEditMode ? (
                              <EditableTitleField
                                title={selectedRealMeeting.title}
                                onSave={(title) => renameMeeting(selectedRealMeeting.id, title)}
                                t={t}
                              />
                            ) : (
                              <p className="text-sm font-bold text-recall-text">{selectedRealMeeting.title}</p>
                            )}
                            <p className="mt-0.5 text-recall-textMuted">
                              {formatDateOnly(selectedRealMeeting.started_at ?? selectedRealMeeting.created_at)} ·{" "}
                              {formatTimeOnly(selectedRealMeeting.started_at ?? selectedRealMeeting.created_at)}
                            </p>
                            {isMeetingEditMode ? (
                              <div className="mt-1.5">
                                <EditableLocationField location={selectedRealMeeting.location || ""} onSave={updateMeetingLocation} t={t} />
                              </div>
                            ) : (
                              selectedRealMeeting.location && (
                                <p className="mt-0.5 text-recall-textMuted">
                                  {t.meeting_minutes_location_label}: {selectedRealMeeting.location}
                                </p>
                              )
                            )}
                            <p className="mt-0.5 text-recall-textMuted">
                              {t.meeting_export_section_attendees}:{" "}
                              {attendees.length === 0
                                ? t.meeting_minutes_attendees_none
                                : attendees.map((a) => a.display_name).join(", ")}
                            </p>
                          </div>

                          {/* [변경 - 회의록 탭 개편 요청] 진행방식/장소/참석자/전체내용/관련자료 구조를
                              목적/논의내용/결정사항/추진계획 구조로 전면 교체.
                              meeting_purpose/next_steps는 백엔드에 아직 없는 필드라(추출 단계엔 있지만
                              DB/응답 스키마 미반영) 당분간 항상 비어 보인다 - 값이 오기 시작하면
                              그대로 채워짐. discussion_points는 이미 내려오는 필드라 바로 반영된다. */}
                          <div className="border-t border-recall-border pt-3">
                            <p className="mb-1 font-semibold text-recall-textMuted">
                              {t.meeting_minutes_purpose_label}
                            </p>
                            {summary?.meeting_purpose ? (
                              <p className="whitespace-pre-line text-recall-text leading-relaxed">
                                {summary.meeting_purpose}
                              </p>
                            ) : (
                              <p className="text-recall-textMuted">{t.meeting_minutes_purpose_empty}</p>
                            )}
                          </div>

                          <div className="border-t border-recall-border pt-3">
                            <p className="mb-1 font-semibold text-recall-textMuted">
                              {t.meeting_minutes_discussion_label}
                            </p>
                            {summary?.discussion_points && summary.discussion_points.length > 0 ? (
                              <ul className="list-disc space-y-1 pl-4 text-recall-text leading-relaxed">
                                {summary.discussion_points.map((point, i) => (
                                  <li key={i}>{point}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-recall-textMuted">{t.meeting_minutes_discussion_empty}</p>
                            )}
                          </div>

                          <div className="border-t border-recall-border pt-3">
                            <p className="mb-2 font-semibold text-recall-textMuted">
                              {t.meeting_summary_key_decisions}
                            </p>
                            {decisions.length > 0 && (
                              <ul className="mb-2 space-y-1.5">
                                {decisions.map((d) => (
                                  <DecisionItem
                                    key={d.id}
                                    decision={d}
                                    isEditing={isMeetingEditMode}
                                    onSave={(input) => updateDecision(d.id, input)}
                                    t={t}
                                  />
                                ))}
                              </ul>
                            )}
                            {isMeetingEditMode && <AddDecisionForm onAdd={addDecision} t={t} />}
                          </div>

                          {summary?.next_steps && (
                            <div className="border-t border-recall-border pt-3">
                              <p className="mb-1 font-semibold text-recall-textMuted">
                                {t.meeting_minutes_next_steps_label}
                              </p>
                              <p className="whitespace-pre-line text-recall-text leading-relaxed">
                                {summary.next_steps}
                              </p>
                            </div>
                          )}
                        </div>
                      );
                    })()
                  ) : segments.length === 0 ? (
                    <p className="text-xs text-recall-textMuted">{t.meeting_no_script}</p>
                  ) : (
                    <div className="space-y-3 text-xs text-recall-textMuted">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex-1">
                          <UnmappedSpeakerChips
                            labels={uniqueRawSpeakerLabels(segments.map((s) => s.speaker_label))}
                            onAssign={mapSpeakerNames}
                            t={t}
                          />
                        </div>
                        {bulkEditDrafts ? (
                          <div className="flex flex-shrink-0 gap-1.5">
                            <button
                              onClick={cancelBulkEdit}
                              disabled={isBulkSaving}
                              className="rounded-lg border border-recall-border px-2.5 py-1 text-[11px] text-recall-textMuted hover:bg-white/5 disabled:opacity-50"
                            >
                              {t.task_cancel}
                            </button>
                            <button
                              onClick={saveBulkEdit}
                              disabled={isBulkSaving}
                              className="rounded-lg bg-recall-accent px-2.5 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
                            >
                              {isBulkSaving ? t.meeting_export_saving : t.task_save}
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={startBulkEdit}
                            className="flex flex-shrink-0 items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1 text-[11px] text-recall-text hover:bg-white/5"
                          >
                            <PencilIcon size={11} />
                            {t.meeting_bulk_edit_btn}
                          </button>
                        )}
                      </div>
                      {segments
                        .slice()
                        .sort((a, b) => a.segment_index - b.segment_index)
                        .map((s) => (
                          <div
                            key={s.id}
                            id={`segment-${s.id}`}
                            className={`rounded-lg transition-colors duration-500 ${
                              highlightSegmentId === s.id ? "bg-recall-accent/15" : ""
                            }`}
                          >
                            <SegmentRow
                              speakerLabel={s.speaker_label}
                              avatarImageUrl={s.speaker_label ? avatarUrlByName[s.speaker_label] : null}
                              timeMs={s.start_ms}
                              content={s.content}
                              segmentId={s.id}
                              speakerNameOptions={registeredSpeakerNames}
                              onAssignSpeaker={assignSegmentSpeaker}
                              onEditContent={updateSegmentContent}
                              onSeekAudio={(ms) => audioPlayerRef.current?.seekTo(ms)}
                              onSplit={(id) => setSplitTargetSegmentId(id)}
                              bulkEditValue={bulkEditDrafts ? bulkEditDrafts[s.id] ?? s.content : undefined}
                              onBulkEditChange={(value) =>
                                setBulkEditDrafts((prev) => (prev ? { ...prev, [s.id]: value } : prev))
                              }
                              t={t}
                            />
                          </div>
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
          title={t.meeting_contradiction_list_expand}
          className="group relative flex h-full w-8 flex-shrink-0 flex-col items-center gap-2 border-l border-recall-border py-3 text-recall-textMuted transition-colors hover:border-recall-accent/40 hover:bg-white/5"
        >
          {contradictions.length > 0 && (
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-recall-accent text-[10px] font-semibold text-white">
              {contradictions.length}
            </span>
          )}
          {meetingReminders.filter((r) => !r.is_read).length > 0 && (
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-amber-500 text-[10px] font-semibold text-white">
              {meetingReminders.filter((r) => !r.is_read).length}
            </span>
          )}
          <ChevronLeftIcon size={11} className="opacity-50 transition-opacity group-hover:opacity-100" />
        </button>
      ) : (
        <div className="flex h-full w-72 flex-shrink-0 flex-col border-l border-recall-border p-3">
          <div className="mb-2 flex items-center gap-1.5">
            <button
              onClick={() => setIsContradictionListOpen(false)}
              title={t.meeting_contradiction_list_collapse}
              className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded hover:bg-white/5"
            >
              <ChevronRightIcon size={13} className="text-recall-textMuted" />
            </button>
            <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-recall-textMuted">
              {t.contradiction_title}
            </p>
          </div>

          {meetingReminders.length > 0 && (
            <div className="mb-3 space-y-1.5 border-b border-recall-border pb-3">
              <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-recall-textMuted">
                {t.meeting_live_alert_reminder_title}
                <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold normal-case tracking-normal">
                  {meetingReminders.length}
                </span>
              </p>
              {meetingReminders.map((r) => (
                <button
                  key={r.id}
                  onClick={() => !r.is_read && markReminderRead(r.id)}
                  className={`block w-full rounded-lg border px-2.5 py-2 text-left text-xs transition ${
                    r.is_read
                      ? "border-recall-border/50 text-recall-textMuted hover:bg-white/5"
                      : "border-amber-500/30 bg-amber-500/5 text-recall-text hover:bg-amber-500/10"
                  }`}
                >
                  {r.message}
                </button>
              ))}
            </div>
          )}

          {/* 미해결 안건 리마인더 - 예전엔 회의 시작 시 카드 팝업으로만 잠깐 떴다가 넘기면
              완전히 사라져서 회의 중간에 다시 확인할 방법이 없었다. 팝업이 떠 있는 동안엔
              여기 목록에도 같이 보여서, 회의 중에도 접었다 펼쳐서 다시 볼 수 있게 한다. */}
          {agendaReminder && agendaReminder.items.length > 0 && (
            <div className="mb-3 space-y-1.5 border-b border-recall-border pb-3">
              <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-recall-textMuted">
                {t.meeting_live_alert_agenda_title}
                <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold normal-case tracking-normal">
                  {agendaReminder.items.length}
                </span>
              </p>
              {agendaReminder.items.map((item) => (
                <div
                  key={item.id}
                  className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-2.5 py-2 text-xs text-recall-text"
                >
                  <p className="font-semibold">{item.title}</p>
                  <p className="mt-0.5 text-recall-textMuted">{item.decision_text}</p>
                </div>
              ))}
            </div>
          )}

          {isViewingLive ? (
            <p className="mb-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-2.5 py-2 text-xs text-amber-400">
              {t.meeting_live_contradiction_notice}
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
                const isDecisionCard = c.reference_type === "decision";
                const caseDisplay = isDecisionCard && c.judgment_case ? decisionCaseDisplay(t, c.judgment_case) : null;
                return (
                  <div
                    key={c.id}
                    onClick={() => toggleContradictionExpanded(c.id)}
                    className={`cursor-pointer rounded-xl border p-2.5 transition ${
                      caseDisplay
                        ? `${caseDisplay.borderClass} hover:opacity-90`
                        : "border-recall-border/80 bg-recall-bgSoft/40 hover:border-recall-accent/50"
                    }`}
                  >
                    <div className="mb-1 flex items-center justify-between gap-1">
                      {caseDisplay ? (
                        <span className={`flex items-center gap-1 text-[11px] font-bold ${caseDisplay.colorClass}`}>
                          <caseDisplay.Icon size={12} className="flex-shrink-0" />
                          {caseDisplay.title}
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-[11px] font-medium text-recall-textMuted">
                          {c.source_type === "meeting_segment" ? (
                            <MicIcon size={11} className="flex-shrink-0" />
                          ) : (
                            <DocumentIcon size={11} className="flex-shrink-0" />
                          )}
                          {c.source_type === "meeting_segment" ? t.contradiction_source_meeting : t.contradiction_source_chat}
                        </span>
                      )}
                      {/* severity(모순 심각도)는 문서-발화 모순 감지 전용 개념이라 decision 카드에서는 숨긴다 */}
                      {!isDecisionCard && severityBadge(c.severity, t)}
                    </div>
                    {editingContradictionId === c.id ? (
                      <ContradictionEditForm
                        contradiction={c}
                        onCancel={() => setEditingContradictionId(null)}
                        onSave={async (updates) => {
                          const ok = await updateContradiction(c.id, updates);
                          if (ok) setEditingContradictionId(null);
                          return ok;
                        }}
                        t={t}
                      />
                    ) : (
                      <ContradictionMessage
                        contradiction={c}
                        expanded={isExpanded}
                        onViewReference={(id, name) => setPreviewDoc({ id, name })}
                        onViewDecision={(decisionId) => onOpenDecision(decisionId)}
                        t={t}
                      />
                    )}
                    {!isViewingLive && editingContradictionId !== c.id && (
                      <div className="flex gap-1 pt-1" onClick={(e) => e.stopPropagation()}>
                        {c.status === "unresolved" ? (
                          <>
                            <button
                              onClick={() => setEditingContradictionId(c.id)}
                              className="flex-1 rounded border border-recall-border px-1.5 py-1 text-[11px] text-recall-textMuted hover:bg-white/5"
                            >
                              {t.contradiction_edit}
                            </button>
                            <button
                              onClick={() => resolve(c.id, "keep_reference")}
                              className="flex-1 rounded border border-recall-border px-1.5 py-1 text-[11px] text-recall-text hover:bg-white/5"
                            >
                              {t.contradiction_keep}
                            </button>
                            {/* 채팅에서 감지된 결정 변경(reference_type === "decision")만 백엔드가
                                여전히 409로 막는다 - 회의에서 감지된 결정 변경은 그대로 반영 가능하므로
                                채팅 소스일 때만 숨긴다 */}
                            {!(c.source_type === "room_message" && isDecisionCard) && (
                              <button
                                onClick={async () => {
                                  const ok = await showConfirm(t.contradiction_apply_confirm, t.contradiction_apply, t.task_cancel);
                                  if (ok) resolve(c.id, "change_acknowledged");
                                }}
                                className="flex-1 rounded bg-recall-accent px-1.5 py-1 text-[11px] font-medium text-white hover:opacity-90"
                              >
                                {t.contradiction_apply}
                              </button>
                            )}
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
      </div>
      )}

      {/* 모달 연동 */}
      {showUploadModal && (
        <UploadModal
          isUploading={isUploading}
          onClose={() => setShowUploadModal(false)}
          onUpload={handleUpload}
          t={t}
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
          t={t}
        />
      )}

      {splitTargetSegmentId && (() => {
        const target = segments.find((s) => s.id === splitTargetSegmentId);
        if (!target) return null;
        return (
          <SplitSegmentModal
            segment={target}
            onClose={() => setSplitTargetSegmentId(null)}
            onSplit={(id, params: SplitSegmentParams) => splitSegment(id, params)}
            t={t}
          />
        );
      })()}

      {showAttendeesModal && selectedRealMeeting && (
        <MeetingAttendeesModal
          workspaceId={workspaceId}
          meetingId={selectedRealMeeting.id}
          meetingTitle={selectedRealMeeting.title}
          onClose={() => setShowAttendeesModal(false)}
          onSaved={reloadAttendees}
          t={t}
        />
      )}

      {showExportModal && selectedRealMeeting && (
        <MeetingExportModal
          workspaceId={workspaceId}
          meetingId={selectedRealMeeting.id}
          onClose={() => setShowExportModal(false)}
          t={t}
        />
      )}

      {showStartModal && (
        <MeetingStartModal
          workspaceId={workspaceId}
          currentUserId={currentUserId}
          defaultTitle={defaultMeetingTitle()}
          onClose={() => setShowStartModal(false)}
          categories={categoriesState.categories}
          suggestedCategoryId={categoriesState.suggestedCategoryId}
          lockedCategory={startCategoryId ? categoryById.get(startCategoryId) ?? null : null}
          onCreateCategory={categoriesState.createCategory}
          onStart={(title, attendeeIds, location, recordingMode, categoryId) => {
            setShowStartModal(false);
            if (categoryId) categoriesState.markCategoryUsed(categoryId);
            onStartLive(title, undefined, attendeeIds, location, recordingMode, categoryId);
          }}
          t={t}
        />
      )}
    </div>
  );
}