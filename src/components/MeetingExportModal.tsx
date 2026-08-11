import { useEffect, useState } from "react";
import jsPDF from "jspdf";
import html2canvas from "html2canvas";
import {
  getMeetingExportApi,
  exportMeetingPdfApi,
  getMeetingSummaryApi,
  getMeetingDecisionsApi,
  MeetingExportData,
  Decision,
} from "../services/meeting";
import { CloseIcon } from "./icons";

interface MeetingExportModalProps {
  workspaceId: string;
  meetingId: string;
  onClose: () => void;
  t: any;
}

interface SectionFlags {
  summary: boolean;
  fullSummary: boolean;
  decisions: boolean;
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
@page {
  size: A4;
  margin: 20mm 16mm;
}
@media print {
  body * { visibility: hidden; }
  #meeting-export-print-area, #meeting-export-print-area * { visibility: visible; }
  #meeting-export-print-area { position: absolute; left: 0; top: 0; width: 100%; }
}
`;

// "서버에 저장"(html2canvas 캡처) 경로는 @media print를 타지 않으므로, 화면에서 숨길 요소는
// 이 클래스로 표시해두고 캡처 시 ignoreElements로 걸러낸다.
const PDF_EXPORT_HIDE_CLASS = "pdf-export-hide";
const PDF_MARGIN_PT = 36; // ~0.5in, 서버 저장 PDF의 상하좌우 여백

export default function MeetingExportModal({ workspaceId, meetingId, onClose, t }: MeetingExportModalProps) {
  const [data, setData] = useState<MeetingExportData | null>(null);
  const [fullSummary, setFullSummary] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [sections, setSections] = useState<SectionFlags>({
    summary: true,
    fullSummary: true,
    decisions: true,
    attendees: true,
    script: true,
  });

  // 서버에 PDF로 저장
  const [isExportingPdf, setIsExportingPdf] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportSuccessMsg, setExportSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      // 회의록 탭에서 수정한 전체 내용/결정사항까지 내보내기에 반영되도록, export 전용
      // 엔드포인트에 없는 두 필드는 회의 상세 화면과 같은 API로 따로 가져와서 합친다.
      const [exportRes, summaryRes, decisionsRes] = await Promise.all([
        getMeetingExportApi(workspaceId, meetingId),
        getMeetingSummaryApi(workspaceId, meetingId),
        getMeetingDecisionsApi(workspaceId, meetingId),
      ]);
      if (!cancelled) {
        if (exportRes.status === "success") setData(exportRes.data);
        if (summaryRes.status === "success") setFullSummary(summaryRes.summary?.full_summary || null);
        if (decisionsRes.status === "success") setDecisions(decisionsRes.decisions);
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

  async function saveToServer() {
    if (!data) return;
    setIsExportingPdf(true);
    setExportError(null);
    setExportSuccessMsg(null);

    try {
      const printArea = document.getElementById("meeting-export-print-area");
      if (!printArea) throw new Error("no-print-area");

      const canvas = await html2canvas(printArea, {
        scale: 2,
        backgroundColor: "#ffffff",
        ignoreElements: (el) => el.classList.contains(PDF_EXPORT_HIDE_CLASS),
      });

      const pdf = new jsPDF({ unit: "pt", format: "a4" });
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const contentWidthPt = pageWidth - PDF_MARGIN_PT * 2;
      const contentHeightPt = pageHeight - PDF_MARGIN_PT * 2;

      // 캔버스 px -> pt 변환 비율 (여백을 뺀 콘텐츠 너비 기준)
      const pxPerPt = canvas.width / contentWidthPt;
      const pageHeightPx = contentHeightPt * pxPerPt;

      let renderedHeightPx = 0;
      let isFirstPage = true;
      while (renderedHeightPx < canvas.height) {
        const sliceHeightPx = Math.min(pageHeightPx, canvas.height - renderedHeightPx);

        const sliceCanvas = document.createElement("canvas");
        sliceCanvas.width = canvas.width;
        sliceCanvas.height = sliceHeightPx;
        const ctx = sliceCanvas.getContext("2d");
        if (!ctx) throw new Error("no-canvas-context");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, sliceCanvas.width, sliceCanvas.height);
        ctx.drawImage(
          canvas,
          0,
          renderedHeightPx,
          canvas.width,
          sliceHeightPx,
          0,
          0,
          canvas.width,
          sliceHeightPx
        );

        if (!isFirstPage) pdf.addPage();
        pdf.addImage(
          sliceCanvas.toDataURL("image/png"),
          "PNG",
          PDF_MARGIN_PT,
          PDF_MARGIN_PT,
          contentWidthPt,
          sliceHeightPx / pxPerPt
        );

        renderedHeightPx += sliceHeightPx;
        isFirstPage = false;
      }

      const blob = pdf.output("blob");
      const filename = `${data.title || t.meeting_top_tab_exports}.pdf`;
      const res = await exportMeetingPdfApi(workspaceId, meetingId, blob, filename);

      if (res.status === "error") {
        setExportError(res.message);
      } else {
        setExportSuccessMsg(t.meeting_export_save_success);
      }
    } catch {
      setExportError(t.meeting_export_pdf_gen_failed);
    } finally {
      setIsExportingPdf(false);
    }
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
          <p className="text-base font-semibold">{t.meeting_export_title}</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        {isLoading ? (
          <p className="px-6 py-8 text-base text-recall-textMuted">{t.common_loading}</p>
        ) : !data ? (
          <p className="px-6 py-8 text-base text-recall-danger">{t.meeting_export_load_failed}</p>
        ) : (
          <>
            {/* 포함할 항목 선택 - 기본은 다 선택됨 */}
            <div className="flex flex-wrap gap-3 border-b border-recall-border px-6 py-3">
              {(
                [
                  { key: "summary" as const, label: t.tab_summary },
                  { key: "fullSummary" as const, label: t.meeting_minutes_content_label },
                  { key: "decisions" as const, label: t.meeting_summary_key_decisions },
                  { key: "attendees" as const, label: t.meeting_export_section_attendees },
                  { key: "script" as const, label: t.meeting_tab_script },
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
                      {t.meeting_export_section_attendees}
                    </p>
                    {data.attendees.length === 0 ? (
                      <p className="text-sm text-recall-textMuted">{t.meeting_minutes_attendees_none}</p>
                    ) : (
                      <p className="text-sm text-recall-text">
                        {data.attendees.map((a) => a.display_name).join(", ")}
                      </p>
                    )}
                  </div>
                )}

                {sections.summary && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                      {t.tab_summary}
                    </p>
                    <p className="whitespace-pre-line text-sm text-recall-text">
                      {data.short_summary || t.meeting_summary_not_ready}
                    </p>
                  </div>
                )}

                {sections.fullSummary && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                      {t.meeting_minutes_content_label}
                    </p>
                    <p className="whitespace-pre-line text-sm text-recall-text">
                      {fullSummary || t.meeting_minutes_content_empty}
                    </p>
                  </div>
                )}

                {sections.decisions && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                      {t.meeting_summary_key_decisions}
                    </p>
                    {decisions.length === 0 ? (
                      <p className="text-sm text-recall-textMuted">{t.meeting_no_decisions}</p>
                    ) : (
                      <ul className="space-y-1">
                        {decisions.map((d) => (
                          <li key={d.id} className="text-sm text-recall-text">
                            <span className="font-medium">{d.title}</span>
                            <span className="text-recall-textMuted"> — {d.decision_text}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {sections.script && (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                      {t.meeting_tab_script}
                    </p>
                    {sortedSegments.length === 0 ? (
                      <p className="text-sm text-recall-textMuted">{t.meeting_no_script}</p>
                    ) : (
                      <div className="space-y-1.5">
                        {sortedSegments.map((s) => (
                          <p key={s.id} className="text-sm text-recall-text">
                            <span className="font-medium">{s.speaker_label || t.speaker_unknown}</span>
                            <span className="text-recall-textMuted"> · {s.content}</span>
                            {s.is_edited && (
                              <span className="ml-1.5 text-[10px] text-amber-400">{t.meeting_export_edited_badge}</span>
                            )}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-recall-border px-6 py-4">
              {exportError && <p className="mr-auto text-xs text-recall-danger">{exportError}</p>}
              {exportSuccessMsg && <p className="mr-auto text-xs text-emerald-500">{exportSuccessMsg}</p>}
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-recall-border px-3.5 py-2 text-sm text-recall-textMuted hover:bg-white/5"
              >
                {t.btn_close}
              </button>
              <button
                type="button"
                onClick={() => window.print()}
                className="rounded-lg border border-recall-border px-4 py-2 text-sm font-medium text-recall-text hover:bg-white/5"
              >
                {t.meeting_export_save_pdf}
              </button>
              <button
                type="button"
                onClick={saveToServer}
                disabled={isExportingPdf}
                className="rounded-lg bg-recall-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
              >
                {isExportingPdf ? t.meeting_export_saving : t.meeting_export_save_server}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
