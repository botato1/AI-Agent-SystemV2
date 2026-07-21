// src/components/DocumentAnalysisView.tsx
import { useRef } from "react";
import { AnalyzedDocument } from "../types"; // 전역 types.ts로부터 직접 가져와 충돌 원천 차단
import { DocumentIcon, SparklesIcon, UploadIcon } from "./icons";

interface DocumentAnalysisViewProps {
  documents: AnalyzedDocument[];
  activeDocId: string | null;
  uploadDocument: (fileList: FileList | null) => void;
  selectDocument: (id: string | null) => void;
  t: any;
}

export default function DocumentAnalysisView({
  documents,
  activeDocId,
  uploadDocument,
  selectDocument,
  t,
}: DocumentAnalysisViewProps) {
  const activeDoc = documents.find((d) => d.id === activeDocId) ?? null;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isKo = t.settings_lang === "언어";

  return (
    <div className="flex h-full w-full bg-recall-bgMain text-recall-text">
      {/* 왼쪽 문서 목록 */}
      <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-recall-textMuted">
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
            className="rounded-lg border border-recall-border px-2.5 py-1 text-xs hover:bg-white/5"
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
                <span className="flex items-center gap-1.5 text-xs font-medium">
                  {doc.status === "analyzing" && (
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-recall-accent" />
                  )}
                  <span className="truncate">{doc.name}</span>
                </span>
                <span className="text-[10px] text-recall-textMuted">
                  {doc.status === "analyzing" ? t.analyzing_msg : "DOCUMENT"}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 오른쪽 상세 */}
      {activeDoc ? (
        <div className="flex flex-1 flex-col p-4 overflow-hidden">
          <div className="mb-3">
            <p className="text-sm font-medium">{activeDoc.name}</p>
            <p className="text-xs text-recall-textMuted">DOCUMENT</p>
          </div>

          {activeDoc.status === "analyzing" ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
              <p className="text-sm text-recall-textMuted">{t.analyzing_msg}</p>
            </div>
          ) : (
            <div className="grid flex-1 grid-cols-2 gap-4 overflow-hidden">
              {/* 요약 패널 */}
              <div className="flex flex-col rounded-xl border border-recall-border bg-recall-bgSoft p-4">
                <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
                  <SparklesIcon size={14} className="text-recall-accent" />
                  {t.doc_tab_summary}
                </p>
                <p className="flex-1 overflow-y-auto text-sm leading-relaxed whitespace-pre-wrap">
                  {isKo ? activeDoc.summary : "This document defines the key standards and implementation guidelines for the project. Core components are aligned to avoid architecture redundancy."}
                </p>
              </div>

              {/* 키워드 & 원본 미리보기 패널 */}
              <div className="flex flex-col gap-4 overflow-hidden">
                <div className="rounded-xl border border-recall-border bg-recall-bgSoft p-4">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
                    {t.doc_tab_keywords}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {activeDoc.keywords?.map((kw: string) => (
                      <span
                        key={kw}
                        className="rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1 text-xs text-recall-text"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex flex-1 flex-col rounded-xl border border-recall-border bg-recall-bgSoft p-4">
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
                    {t.doc_tab_original}
                  </p>
                  <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-recall-border bg-recall-bgMain p-4 text-center">
                    <div>
                      <DocumentIcon size={24} className="mx-auto mb-2 text-recall-textMuted" />
                      <p className="text-xs text-recall-textMuted">{t.original_not_supported}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-2">
          <UploadIcon size={24} className="text-recall-textMuted" />
          <p className="text-sm text-recall-textMuted">{t.doc_not_selected}</p>
        </div>
      )}
    </div>
  );
}