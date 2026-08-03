import { useEffect, useState } from "react";
import {
  getMeetingExportApi,
  updateMeetingSummaryApi,
  updateMeetingSegmentApi,
  MeetingExportData,
} from "../services/meeting";
import { CloseIcon } from "./icons";

interface MeetingExportModalProps {
  workspaceId: string;
  meetingId: string;
  onClose: () => void;
}

interface SectionFlags {
  summary: boolean;
  attendees: boolean;
  script: boolean;
}

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.getFullYear()}. ${d.getMonth() + 1}. ${d.getDate()}. ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

// PDF 라이브러리 없이, 브라우저 인쇄(다른 이름으로 저장 -> PDF)로 내보낸다. 인쇄할 때
// 이 영역만 보이게 하고 나머지 화면(모달 배경 등)은 다 숨긴다.
const PRINT_STYLE = `
@media print {
  body * { visibility: hidden; }
  #meeting-export-print-area, #meeting-export-print-area * { visibility: visible; }
  #meeting-export-print-area { position: absolute; left: 0; top: 0; width: 100%; }
}
`;

export default function MeetingExportModal({ workspaceId, meetingId, onClose }: MeetingExportModalProps) {
  const [data, setData] = useState<MeetingExportData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sections, setSections] = useState<SectionFlags>({ summary: true, attendees: true, script: true });

  // 요약 인라인 수정 상태
  const [isEditingSummary, setIsEditingSummary] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [isSavingSummary, setIsSavingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // 스크립트(발화 세그먼트) 인라인 수정 상태 - STT 오인식 정정용
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [segmentDraft, setSegmentDraft] = useState("");
  const [isSavingSegment, setIsSavingSegment] = useState(false);
  const [segmentError, setSegmentError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      const res = await getMeetingExportApi(workspaceId, meetingId);
      if (!cancelled && res.status === "success") {
        setData(res.data);
      }
      setIsLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, meetingId]);

  function toggleSection(key: keyof SectionFlags) {
    setSections((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function startEditSummary() {
    if (!data) return;
    setSummaryError(null);
    setSummaryDraft(data.short_summary || "");
    setIsEditingSummary(true);
  }

  async function saveSummary() {
    if (!data) return;
    setIsSavingSummary(true);
    setSummaryError(null);

    const res = await updateMeetingSummaryApi(workspaceId, meetingId, summaryDraft.trim());

    setIsSavingSummary(false);

    if (res.status === "error") {
      setSummaryError(res.message);
      return;
    }

    setData((prev) => (prev ? { ...prev, short_summary: summaryDraft.trim() } : prev));
    setIsEditingSummary(false);
  }

  function startEditSegment(segmentId: string, currentContent: string) {
    setSegmentError(null);
    setEditingSegmentId(segmentId);
    setSegmentDraft(currentContent);
  }

  async function saveSegment(segmentId: string) {
    if (!data) return;
    setIsSavingSegment(true);
    setSegmentError(null);

    const res = await updateMeetingSegmentApi(workspaceId, meetingId, segmentId, segmentDraft.trim());

    setIsSavingSegment(false);

    if (res.status === "error") {
      setSegmentError(res.message);
      return;
    }

    setData((prev) =>
      prev
        ? {
            ...prev,
            segments: prev.segments.map((s) =>
              s.id === segmentId ? { ...s, content: segmentDraft.trim(), is_edited: true } : s
            ),
          }
        : prev
    );
    setEditingSegmentId(null);
  }

  const sortedSegments = data ? [...data.segments].sort((a, b) => a.segment_index - b.segment_index) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <style>{PRINT_STYLE}</style>
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-recall-border bg-recall-bg shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-recall-border px-6 py-4">
          <p className="text-base font-semibold">회의록 내보내기</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        {isLoading ? (
          <p className="px-6 py-8 text-base text-recall-textMuted">불러오는 중...</p>
        ) : !data ? (
          <p className="px-6 py-8 text-base text-recall-danger">회의록 데이터를 불러오지 못했습니다.</p>
        ) : (
          <>
            {/* 포함할 항목 선택 - 기본은 다 선택됨 */}
            <div className="flex flex-wrap gap-3 border-b border-recall-border px-6 py-3">
              {(
                [
                  { key: "summary" as const, label: "요약" },
                  { key: "attendees" as const, label: "참석자" },
                  { key: "script" as const, label: "스크립트" },
                ]
              ).map((item) => (
                <label key={item.key} className="flex items-center gap-1.5 text-sm text-recall-text">
                  <input
                    type="checkbox"
                    checked={sections[item.key]}
                    onChange={() => toggleSection(item.key)}
                    className="accent-recall-accent"
                  />
                  {item.label}
                </label>
              ))}
            </div>

            {/* 미리보기 - 인쇄(PDF 저장) 시 이 영역만 출력됨 */}
            <div className="flex-1 overflow-y-auto px-6 py-5">
              <div id="meeting-export-print-area" className="space-y-4 text-recall-text">
                <div>
                  <p className="text-lg font-bold">{data.title}</p>
                  <p className="mt-1 text-sm text-recall-textMuted">
                    {formatDate(data.started_at)}
                    {data.location ? ` · ${data.location}` : ""}
                  </p>
                </div>

                {sections.attendees && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                      참석자
                    </p>
                    {data.attendees.length === 0 ? (
                      <p className="text-sm text-recall-textMuted">지정된 참석자가 없습니다.</p>
                    ) : (
                      <p className="text-sm text-recall-text">
                        {data.attendees.map((a) => a.display_name).join(", ")}
                      </p>
                    )}
                  </div>
                )}

                {sections.summary && (
                  <div>
                    <div className="mb-1 flex items-center justify-between">
                      <p className="text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                        요약
                      </p>
                      {!isEditingSummary && (
                        <button
                          type="button"
                          onClick={startEditSummary}
                          className="print:hidden text-[11px] text-recall-textMuted underline hover:text-recall-text"
                        >
                          수정
                        </button>
                      )}
                    </div>

                    {isEditingSummary ? (
                      <div className="print:hidden flex flex-col gap-2">
                        <textarea
                          value={summaryDraft}
                          onChange={(e) => setSummaryDraft(e.target.value)}
                          rows={4}
                          className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-3 py-2 text-sm text-recall-text outline-none focus:border-recall-accent"
                        />
                        {summaryError && <p className="text-xs text-recall-danger">{summaryError}</p>}
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setIsEditingSummary(false)}
                            disabled={isSavingSummary}
                            className="rounded-lg border border-recall-border px-3 py-1.5 text-xs text-recall-textMuted hover:bg-white/5"
                          >
                            취소
                          </button>
                          <button
                            type="button"
                            onClick={saveSummary}
                            disabled={isSavingSummary}
                            className="rounded-lg bg-recall-accent px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
                          >
                            {isSavingSummary ? "저장 중..." : "저장"}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="whitespace-pre-line text-sm text-recall-text">
                        {data.short_summary || "아직 요약이 생성되지 않았습니다."}
                      </p>
                    )}
                  </div>
                )}

                {sections.script && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                      스크립트
                    </p>
                    {sortedSegments.length === 0 ? (
                      <p className="text-sm text-recall-textMuted">발화 스크립트가 없습니다.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {segmentError && <p className="print:hidden text-xs text-recall-danger">{segmentError}</p>}
                        {sortedSegments.map((s) =>
                          editingSegmentId === s.id ? (
                            <div key={s.id} className="print:hidden flex flex-col gap-1.5">
                              <span className="text-xs font-medium text-recall-text">
                                {s.speaker_label || "화자 미상"}
                              </span>
                              <textarea
                                value={segmentDraft}
                                onChange={(e) => setSegmentDraft(e.target.value)}
                                rows={2}
                                className="w-full rounded-lg border border-recall-border bg-recall-bgSoft px-2.5 py-1.5 text-sm text-recall-text outline-none focus:border-recall-accent"
                              />
                              <div className="flex justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={() => setEditingSegmentId(null)}
                                  disabled={isSavingSegment}
                                  className="rounded-lg border border-recall-border px-2.5 py-1 text-[11px] text-recall-textMuted hover:bg-white/5"
                                >
                                  취소
                                </button>
                                <button
                                  type="button"
                                  onClick={() => saveSegment(s.id)}
                                  disabled={isSavingSegment}
                                  className="rounded-lg bg-recall-accent px-2.5 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
                                >
                                  {isSavingSegment ? "저장 중..." : "저장"}
                                </button>
                              </div>
                            </div>
                          ) : (
                            <p key={s.id} className="group text-sm text-recall-text">
                              <span className="font-medium">{s.speaker_label || "화자 미상"}</span>
                              <span className="text-recall-textMuted"> · {s.content}</span>
                              {s.is_edited && (
                                <span className="ml-1.5 text-[10px] text-amber-400">(수정됨)</span>
                              )}
                              <button
                                type="button"
                                onClick={() => startEditSegment(s.id, s.content)}
                                className="print:hidden ml-1.5 text-[11px] text-recall-textMuted underline opacity-0 group-hover:opacity-100 hover:text-recall-text"
                              >
                                수정
                              </button>
                            </p>
                          )
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-recall-border px-6 py-4">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-recall-border px-3.5 py-2 text-sm text-recall-textMuted hover:bg-white/5"
              >
                닫기
              </button>
              <button
                type="button"
                onClick={() => window.print()}
                className="rounded-lg bg-recall-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
              >
                PDF로 저장
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
