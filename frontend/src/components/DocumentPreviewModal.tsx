import { useEffect, useState } from "react";
import { DocumentDetail, getDocumentApi } from "../services/document";
import { CloseIcon, DocumentIcon } from "./icons";
import { cleanExtractedText } from "./DocumentContentBlocks";
import DocumentOriginalViewer from "./DocumentOriginalViewer";

interface DocumentPreviewModalProps {
  workspaceId: string;
  documentId: string;
  documentName: string;
  onClose: () => void;
  t: any;
}

type DetailTab = "summary" | "original";

function formatDocDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

export default function DocumentPreviewModal({
  workspaceId,
  documentId,
  documentName,
  onClose,
  t,
}: DocumentPreviewModalProps) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<DetailTab>("summary");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      const detailRes = await getDocumentApi(workspaceId, documentId);
      if (!cancelled) {
        setDetail(detailRes.status === "success" ? detailRes.document : null);
        setIsLoading(false);
        setActiveTab("summary");
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, documentId]);

  // 원본 파일 보기는 분석 결과(청크/요약)가 아니라 파일 원본을 그대로 다시 받아오는 것이라
  // 분석이 끝나기 전(pending/processing)이어도 항상 볼 수 있다.
  const hasOriginal = !!detail;
  const hasSummary = !!detail?.analysis.summary;
  // 요약/원문 둘 다 있을 때만 탭으로 전환하고, 하나만 있으면 그냥 그거 하나만 보여준다
  const showTabs = hasSummary && hasOriginal;
  const visibleTab: DetailTab = showTabs ? activeTab : hasSummary ? "summary" : "original";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl border border-recall-border bg-recall-bgSoft shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 헤더 카드 - 지금 어떤 문서를 보고 있는지 한눈에 들어오게 */}
        <div className="flex items-start justify-between gap-3 border-b border-recall-border px-6 py-5">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-recall-accent/15 text-recall-accent">
              <DocumentIcon size={18} />
            </div>
            <div className="min-w-0">
              <p className="truncate text-lg font-semibold text-recall-text">{documentName}</p>
              {detail && (
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-recall-textMuted">
                  <span>{formatDocDate(detail.created_at)}</span>
                  {!!detail.analysis.page_count && (
                    <>
                      <span className="opacity-50">·</span>
                      <span>{t.doc_preview_page_count(detail.analysis.page_count)}</span>
                    </>
                  )}
                  {!!detail.analysis.table_count && (
                    <>
                      <span className="opacity-50">·</span>
                      <span>{t.doc_preview_table_count(detail.analysis.table_count)}</span>
                    </>
                  )}
                  {!!detail.analysis.graph_count && (
                    <>
                      <span className="opacity-50">·</span>
                      <span>{t.doc_preview_graph_count(detail.analysis.graph_count)}</span>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
          <button onClick={onClose} className="flex-shrink-0 text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        {showTabs && (
          <div className="flex gap-0.5 border-b border-recall-border px-6">
            {(
              [
                { key: "summary", label: t.doc_tab_summary },
                { key: "original", label: t.doc_tab_original },
              ] as { key: DetailTab; label: string }[]
            ).map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-3 py-2.5 text-sm ${
                  activeTab === tab.key
                    ? "border-b-2 border-recall-accent font-medium text-recall-text"
                    : "text-recall-textMuted hover:text-recall-text"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {isLoading ? (
            <p className="text-base text-recall-textMuted">{t.common_loading}</p>
          ) : !detail ? (
            <p className="text-base text-recall-danger">{t.doc_preview_load_failed}</p>
          ) : !hasSummary && !hasOriginal ? (
            <p className="text-base text-recall-textMuted">{t.doc_preview_empty}</p>
          ) : (
            <>
              {visibleTab === "summary" &&
                (hasSummary ? (
                  <div className="rounded-xl border border-recall-border bg-recall-bgMain p-4">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-recall-textMuted/70">
                      {t.doc_tab_summary}
                    </p>
                    <p className="whitespace-pre-wrap text-base leading-relaxed text-recall-text">
                      {cleanExtractedText(detail.analysis.summary!)}
                    </p>
                  </div>
                ) : (
                  <p className="text-base text-recall-textMuted">
                    {detail.analysis_status === "failed" ? t.doc_analysis_failed_msg : t.doc_preview_not_analyzed}
                  </p>
                ))}

              {visibleTab === "original" && (
                <div className="h-[500px] rounded-xl border border-recall-border bg-recall-bgMain p-2">
                  <DocumentOriginalViewer
                    workspaceId={workspaceId}
                    documentId={documentId}
                    documentName={documentName}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
