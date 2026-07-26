// src/components/DocumentAnalysisView.tsx
import { useRef, useState } from "react";
import { AnalyzedDocument } from "../types"; // 전역 types.ts로부터 직접 가져와 충돌 원천 차단
import { DocumentDetail, DocumentFigure } from "../services/document";
import { DocumentIcon, SparklesIcon, UploadIcon, TrashIcon } from "./icons";
import WorktreePanel from "./WorktreePanel";
import { cleanExtractedText } from "./DocumentContentBlocks";
import DocumentOriginalPages from "./DocumentOriginalPages";

type AnalysisTab = "document" | "worktree";

interface DocumentAnalysisViewProps {
  workspaceId: string;
  documents: AnalyzedDocument[];
  activeDocId: string | null;
  activeDocDetail?: DocumentDetail | null;
  activeDocFigures?: DocumentFigure[];
  isDetailLoading?: boolean;
  uploadDocument: (fileList: FileList | null) => void;
  selectDocument: (id: string | null) => void;
  deleteDocument?: (id: string) => void;
  retryDocument?: (id: string) => void;
  t: any;
}

export default function DocumentAnalysisView({
  workspaceId,
  documents,
  activeDocId,
  activeDocDetail,
  activeDocFigures,
  isDetailLoading,
  uploadDocument,
  selectDocument,
  deleteDocument,
  retryDocument,
  t,
}: DocumentAnalysisViewProps) {
  const activeDoc = documents.find((d) => d.id === activeDocId) ?? null;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<AnalysisTab>("document");

  if (tab === "worktree") {
    return (
      <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
        <div className="flex gap-0.5 border-b border-recall-border p-3 pb-0">
          <button
            onClick={() => setTab("document")}
            className="px-2 pb-2 text-sm text-recall-textMuted hover:text-recall-text"
          >
            개별 문서
          </button>
          <button
            onClick={() => setTab("worktree")}
            className="border-b-2 border-recall-accent px-2 pb-2 text-sm text-recall-accent"
          >
            코드 폴더
          </button>
        </div>
        <WorktreePanel workspaceId={workspaceId} />
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
      <div className="flex gap-0.5 border-b border-recall-border p-3 pb-0">
        <button
          onClick={() => setTab("document")}
          className="border-b-2 border-recall-accent px-2 pb-2 text-sm text-recall-accent"
        >
          개별 문서
        </button>
        <button
          onClick={() => setTab("worktree")}
          className="px-2 pb-2 text-sm text-recall-textMuted hover:text-recall-text"
        >
          코드 폴더
        </button>
      </div>
      <div className="flex flex-1 overflow-hidden">
      {/* 왼쪽 문서 목록 */}
      <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-medium uppercase tracking-wide text-recall-textMuted">
            {t.doc_list_title}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => uploadDocument(e.target.files)}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="rounded-lg border border-recall-border px-2.5 py-1 text-sm hover:bg-white/5"
          >
            {t.doc_btn_upload}
          </button>
        </div>
        <div className="flex-1 space-y-1.5 overflow-y-auto">
          {documents.map((doc) => {
            const isSelected = doc.id === activeDocId;
            return (
              <button
                key={doc.id}
                onClick={() => selectDocument(doc.id)}
                className={`flex w-full flex-col gap-0.5 rounded-lg border px-2.5 py-2 text-left transition ${
                  isSelected
                    ? "border-recall-accent bg-recall-accent/10"
                    : "border-recall-border hover:bg-white/5"
                }`}
              >
                <span className="flex items-center gap-1.5 text-sm font-medium">
                  {doc.status === "analyzing" && (
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-recall-accent" />
                  )}
                  {doc.status === "failed" && (
                    <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-danger" />
                  )}
                  <span className="truncate">{doc.name}</span>
                </span>
                <span className="text-[11px] text-recall-textMuted">
                  {doc.status === "analyzing"
                    ? t.analyzing_msg
                    : doc.status === "failed"
                    ? "분석 실패"
                    : "DOCUMENT"}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 오른쪽 상세 */}
      {activeDoc ? (
        <div className="flex flex-1 flex-col p-4 overflow-hidden">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-base font-medium">{activeDoc.name}</p>
              <p className="text-sm text-recall-textMuted">DOCUMENT</p>
            </div>
            <div className="flex gap-1.5">
              {activeDoc.status === "failed" && retryDocument && (
                <button
                  onClick={() => retryDocument(activeDoc.id)}
                  className="rounded-lg border border-recall-border px-2.5 py-1.5 text-sm text-recall-text hover:bg-white/5"
                >
                  재분석
                </button>
              )}
              {deleteDocument && (
                <button
                  onClick={() => deleteDocument(activeDoc.id)}
                  className="flex items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1.5 text-sm text-recall-textMuted hover:border-recall-danger hover:text-recall-danger"
                >
                  <TrashIcon size={13} />
                  삭제
                </button>
              )}
            </div>
          </div>

          {activeDoc.status === "analyzing" ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
              <p className="text-base text-recall-textMuted">{t.analyzing_msg}</p>
            </div>
          ) : activeDoc.status === "failed" ? (
            <div className="flex flex-1 items-center justify-center rounded-lg border border-recall-danger/30 bg-recall-danger/5">
              <p className="text-base text-recall-danger">문서 분석에 실패했습니다.</p>
            </div>
          ) : isDetailLoading ? (
            <div className="flex flex-1 items-center justify-center">
              <p className="text-base text-recall-textMuted">불러오는 중...</p>
            </div>
          ) : (
            <div className="grid flex-1 grid-cols-3 gap-4 overflow-hidden">
              {/* 원본 패널 (메인, 2/3 폭) */}
              <div className="col-span-2 flex flex-col rounded-xl border border-recall-border bg-recall-bgSoft p-4 overflow-hidden">
                <p className="mb-2 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
                  {t.doc_tab_original}
                </p>
                {activeDocDetail?.raw.original_text || activeDocDetail?.raw.chunks?.length || activeDocFigures?.length ? (
                  <div className="flex-1 space-y-2 overflow-y-auto text-sm leading-relaxed text-recall-textMuted">
                    <DocumentOriginalPages
                      chunks={activeDocDetail?.raw.chunks ?? []}
                      originalText={activeDocDetail?.raw.original_text ?? null}
                      figures={activeDocFigures ?? []}
                    />
                  </div>
                ) : (
                  <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-recall-border bg-recall-bgMain p-4 text-center">
                    <div>
                      <DocumentIcon size={24} className="mx-auto mb-2 text-recall-textMuted" />
                      <p className="text-sm text-recall-textMuted">{t.original_not_supported}</p>
                    </div>
                  </div>
                )}
              </div>

              {/* 분석 정보 / 이미지 / 요약 패널 (보조, 1/3 폭) */}
              <div className="flex flex-col gap-4 overflow-hidden">
                <div className="rounded-xl border border-recall-border bg-recall-bgSoft p-4">
                  <p className="mb-2 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
                    분석 정보
                  </p>
                  <div className="flex flex-wrap gap-1.5 text-sm text-recall-textMuted">
                    <span className="rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1">
                      페이지 {activeDocDetail?.analysis.page_count ?? "-"}
                    </span>
                    <span className="rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1">
                      표 {activeDocDetail?.analysis.table_count ?? "-"}
                    </span>
                    <span className="rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1">
                      차트 {activeDocDetail?.analysis.graph_count ?? "-"}
                    </span>
                  </div>
                </div>

                <div className="max-h-48 flex-shrink-0 overflow-y-auto rounded-xl border border-recall-border bg-recall-bgSoft p-4">
                  <p className="mb-2 flex items-center gap-1.5 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
                    <SparklesIcon size={14} className="text-recall-accent" />
                    {t.doc_tab_summary}
                  </p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">
                    {activeDocDetail?.analysis.summary
                      ? cleanExtractedText(activeDocDetail.analysis.summary)
                      : "요약이 없습니다."}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-2">
          <UploadIcon size={24} className="text-recall-textMuted" />
          <p className="text-base text-recall-textMuted">{t.doc_not_selected}</p>
        </div>
      )}
      </div>
    </div>
  );
}