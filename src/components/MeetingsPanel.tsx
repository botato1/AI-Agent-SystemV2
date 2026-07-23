import { useEffect, useRef, useState } from "react";
import { useRealMeetings } from "../hooks/useRealMeetings";
import { LiveMeetingStatus, LiveSegment } from "../hooks/useLiveMeeting";
import { Meeting, MeetingStatus } from "../services/meeting";
import { UploadIcon, TrashIcon, DocumentIcon, MicIcon, PauseIcon, PlayIcon, StopIcon } from "./icons";

type DetailTab = "summary" | "decisions" | "script";

const ACCEPTED_EXTENSIONS = ".mp3,.wav,.m4a,.webm";
const LIVE_ACTIVE_STATUSES: LiveMeetingStatus[] = ["connecting", "recording", "paused", "ending"];

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
        <h3 className="mb-4 text-base font-bold">회의 음성 업로드</h3>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-semibold text-recall-textMuted">회의 제목</label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="예: 주간 스프린트 회의"
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-xs text-recall-text outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold text-recall-textMuted">
              음성 파일 (mp3/wav/m4a/webm)
            </label>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-xs text-recall-text outline-none file:mr-2 file:rounded file:border-0 file:bg-recall-accent/15 file:px-2 file:py-1 file:text-recall-accent"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-recall-border px-3.5 py-2 text-xs text-recall-textMuted hover:bg-white/5"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isUploading || !title.trim() || !file}
              className="rounded-lg bg-recall-accent px-3.5 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
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
  liveError: string | null;
  onStartLive: (title: string) => void;
  onPauseLive: () => void;
  onResumeLive: () => void;
  onStopLive: () => void;
  onResetLive: () => void;
}

export default function MeetingsPanel({
  workspaceId,
  liveStatus,
  liveMeeting,
  liveSegments,
  livePartial,
  liveError,
  onStartLive,
  onPauseLive,
  onResumeLive,
  onStopLive,
  onResetLive,
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
    reload,
  } = useRealMeetings(workspaceId);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("summary");

  const isLiveActive = LIVE_ACTIVE_STATUSES.includes(liveStatus);

  // 녹음 중인 회의도 목록의 일반 항목과 똑같이 취급 - id가 같으면 실제 목록 값을 덮어써서 하나로만 보인다
  const meetings: Meeting[] =
    isLiveActive && liveMeeting
      ? [liveMeeting, ...realMeetings.filter((m) => m.id !== liveMeeting.id)]
      : realMeetings;

  const isViewingLive = isLiveActive && !!liveMeeting && selectedMeetingId === liveMeeting.id;

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
      <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-recall-textMuted">회의</p>
          <div className="flex gap-1">
            <button
              onClick={handleStartRecording}
              disabled={isLiveActive}
              title={isLiveActive ? "이미 녹음이 진행 중이에요" : undefined}
              className="flex items-center gap-1 rounded-lg border border-recall-border px-2 py-1 text-[11px] text-recall-text hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <MicIcon size={12} />
              새 녹음
            </button>
            <button
              onClick={() => setShowUploadModal(true)}
              className="flex items-center gap-1 rounded-lg border border-recall-border px-2 py-1 text-[11px] text-recall-text hover:bg-white/5"
            >
              <UploadIcon size={12} />
              업로드
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-1.5 overflow-y-auto">
          {isLoading ? (
            <p className="text-xs text-recall-textMuted">불러오는 중...</p>
          ) : meetings.length === 0 ? (
            <p className="text-xs text-recall-textMuted">아직 회의가 없습니다.</p>
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
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-recall-text">
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
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${badge.className}`}>
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

      {/* 오른쪽 상세 */}
      <div className="flex h-full flex-1 flex-col p-4">
        {isViewingLive && liveMeeting ? (
          <>
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-recall-text">{liveMeeting.title}</p>
                <p className="flex items-center gap-1.5 text-xs text-recall-textMuted">
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
                    className="flex items-center gap-1.5 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
                  >
                    <PauseIcon size={13} />
                    일시정지
                  </button>
                )}
                {liveStatus === "paused" && (
                  <button
                    onClick={onResumeLive}
                    className="flex items-center gap-1.5 rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
                  >
                    <PlayIcon size={13} />
                    재개
                  </button>
                )}
                {(liveStatus === "recording" || liveStatus === "paused") && (
                  <button
                    onClick={onStopLive}
                    className="flex items-center gap-1.5 rounded-lg border border-recall-danger px-2.5 py-1.5 text-xs font-medium text-recall-danger"
                  >
                    <StopIcon size={13} />
                    종료
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border p-3">
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
                <div className="space-y-2 text-sm text-recall-textMuted">
                  {liveSegments.map((s, i) => (
                    <p key={i}>
                      <span className="font-medium text-recall-text">{s.speaker_label || "화자 미상"}</span>{" "}
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
            <p className="text-sm text-recall-danger">{liveError || "오류가 발생했습니다."}</p>
            <button
              onClick={onResetLive}
              className="rounded-lg border border-recall-border px-3.5 py-2 text-xs text-recall-text hover:bg-white/5"
            >
              닫기
            </button>
          </div>
        ) : !selectedRealMeeting ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-recall-textMuted">왼쪽에서 회의를 선택하거나 새로 시작하세요.</p>
          </div>
        ) : (
          <>
            <div className="mb-3">
              <p className="text-sm font-medium text-recall-text">{selectedRealMeeting.title}</p>
              <p className="text-xs text-recall-textMuted">
                {statusBadge(selectedRealMeeting.status).label} · {formatDate(selectedRealMeeting.created_at)}
                {selectedRealMeeting.duration_ms ? ` · ${formatDuration(selectedRealMeeting.duration_ms)}` : ""}
              </p>
            </div>

            {selectedRealMeeting.status === "created" || selectedRealMeeting.status === "processing" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-recall-border">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                <p className="text-sm text-recall-textMuted">음성 분석(STT) 및 요약 생성 중입니다...</p>
              </div>
            ) : selectedRealMeeting.status === "failed" ? (
              <div className="flex flex-1 items-center justify-center rounded-lg border border-recall-danger/30 bg-recall-danger/5">
                <p className="text-sm text-recall-danger">회의 처리에 실패했습니다.</p>
              </div>
            ) : (
              <>
                <div className="mb-3 flex gap-0.5 border-b border-recall-border">
                  {(
                    [
                      { key: "summary", label: "요약" },
                      { key: "decisions", label: "결정사항" },
                      { key: "script", label: "스크립트" },
                    ] as { key: DetailTab; label: string }[]
                  ).map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setDetailTab(tab.key)}
                      className={`px-2 py-1 text-xs ${
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
                    <p className="text-sm text-recall-textMuted">불러오는 중...</p>
                  ) : detailTab === "summary" ? (
                    summary?.generation_status === "completed" ? (
                      <div className="space-y-3">
                        {summary.short_summary && (
                          <p className="text-sm font-medium text-recall-text">{summary.short_summary}</p>
                        )}
                        {summary.full_summary && (
                          <p className="whitespace-pre-line text-sm text-recall-textMuted">
                            {summary.full_summary}
                          </p>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-recall-textMuted">아직 요약이 생성되지 않았습니다.</p>
                    )
                  ) : detailTab === "decisions" ? (
                    decisions.length === 0 ? (
                      <p className="text-sm text-recall-textMuted">추출된 결정사항이 없습니다.</p>
                    ) : (
                      <div className="space-y-3">
                        {decisions.map((d) => (
                          <div key={d.id} className="rounded-lg border border-recall-border p-2.5">
                            <p className="text-sm font-medium text-recall-text">{d.title}</p>
                            <p className="mt-1 text-xs text-recall-textMuted">{d.decision_text}</p>
                            {d.reason && (
                              <p className="mt-1 text-[11px] text-recall-textMuted">사유: {d.reason}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )
                  ) : segments.length === 0 ? (
                    <p className="text-sm text-recall-textMuted">발화 스크립트가 없습니다.</p>
                  ) : (
                    <div className="space-y-2 text-sm text-recall-textMuted">
                      {segments
                        .slice()
                        .sort((a, b) => a.segment_index - b.segment_index)
                        .map((s) => (
                          <p key={s.id}>
                            <span className="font-medium text-recall-text">
                              {s.speaker_label || "화자 미상"}
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

      {showUploadModal && (
        <UploadModal
          isUploading={isUploading}
          onClose={() => setShowUploadModal(false)}
          onUpload={handleUpload}
        />
      )}
    </div>
  );
}
