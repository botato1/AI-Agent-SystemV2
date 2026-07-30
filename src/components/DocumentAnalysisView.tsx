// src/components/DocumentAnalysisView.tsx
import { useRef, useState } from "react";
import { AnalyzedDocument } from "../types"; // 전역 types.ts로부터 직접 가져와 충돌 원천 차단
import { DocumentDetail, DocumentFigure } from "../services/document";
import { UploadIcon, TrashIcon } from "./icons";
import WorktreePanel from "./WorktreePanel";
import DocumentDetailPanel from "./DocumentDetailPanel";

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
        <div className="flex flex-1 overflow-hidden">
          <WorktreePanel workspaceId={workspaceId} t={t} />
        </div>
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
          ) : (
            <DocumentDetailPanel
              detail={activeDocDetail ?? null}
              figures={activeDocFigures ?? []}
              isLoading={!!isDetailLoading}
              t={t}
            />
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