// src/components/DocumentAnalysisView.tsx
import { useRef, useState } from "react";
import { AnalyzedDocument } from "../types";
import { DocumentDetail, DocumentFigure } from "../services/document";
import { Category } from "../services/category";
import { getCategoryColor } from "../utils/categoryColor";
import WorktreePanel from "./WorktreePanel";
import DocumentDetailPanel from "./DocumentDetailPanel";
import DocumentOriginalViewer from "./DocumentOriginalViewer";
import CategoryBadge from "./CategoryBadge";
import { RepeatIcon, TrashIcon } from "./icons";
import { markUploadingDocument, markUploadDocumentDone, useUploadingDocumentWorkspaceIds } from "../lib/uploadDocumentStatus";

type AnalysisTab = "document" | "worktree";
type DetailContentTab = "summary" | "original";

interface DocumentAnalysisViewProps {
  workspaceId: string;
  documents: AnalyzedDocument[];
  activeDocId: string | null;
  activeDocDetail?: DocumentDetail | null;
  activeDocFigures?: DocumentFigure[];
  isDetailLoading?: boolean;
  uploadDocument: (fileList: FileList | null, categoryId?: string) => Promise<void> | void;
  selectDocument: (id: string | null) => void;
  deleteDocument?: (id: string) => void;
  retryDocument?: (id: string) => void;
  categories: Category[];
  selectedCategoryId: string | null;
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
  categories,
  selectedCategoryId,
  t,
}: DocumentAnalysisViewProps) {
  const activeDoc = documents.find((d) => d.id === activeDocId) ?? null;
  // 사이드바 전역 카테고리 선택기 - null("전체")이면 전부, 아니면 그 카테고리 문서만.
  const visibleDocuments = selectedCategoryId
    ? documents.filter((d) => d.category_id === selectedCategoryId)
    : documents;
  const categoryIndexById = new Map(categories.map((c, index) => [c.id, index]));
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<AnalysisTab>("document");
  
  // 요약 정리 vs 원본 파일 보기 탭
  const [detailContentTab, setDetailContentTab] = useState<DetailContentTab>("summary");

  // 페이지를 벗어났다 돌아와도 "업로드 중" 상태가 끊기지 않도록 컴포넌트 로컬 state가
  // 아니라 모듈 전역 상태로 관리한다 (lib/reanalyzeStatus.ts와 동일한 이유).
  const uploadingWorkspaceIds = useUploadingDocumentWorkspaceIds();
  const isUploading = uploadingWorkspaceIds.has(workspaceId);

  const handleFileChange = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;

    markUploadingDocument(workspaceId);

    try {
      await uploadDocument(fileList, selectedCategoryId ?? undefined);
    } catch (error) {
      console.error("파일 업로드 오류:", error);
    } finally {
      markUploadDocumentDone(workspaceId);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileChange(e.dataTransfer.files);
    }
  };

  if (tab === "worktree") {
    return (
      <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
        <div className="flex gap-0.5 border-b border-recall-border p-3 pb-0">
          <button
            onClick={() => setTab("document")}
            className="px-2 pb-2 text-sm text-recall-textMuted hover:text-recall-text"
          >
            {t.doc_tab_individual}
          </button>
          <button
            onClick={() => setTab("worktree")}
            className="border-b-2 border-recall-accent px-2 pb-2 text-sm text-recall-accent font-medium"
          >
            {t.doc_tab_worktree}
          </button>
        </div>
        <div className="flex flex-1 overflow-hidden">
          <WorktreePanel
            workspaceId={workspaceId}
            categories={categories}
            selectedCategoryId={selectedCategoryId}
            t={t}
          />
        </div>
      </div>
    );
  }

  const isDocCompleted = activeDoc && activeDoc.status !== "analyzing" && activeDoc.status !== "failed";

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
      {/* 상단 탭 navigation */}
      <div className="flex gap-0.5 border-b border-recall-border p-3 pb-0">
        <button
          onClick={() => setTab("document")}
          className="border-b-2 border-recall-accent px-2 pb-2 text-sm text-recall-accent font-medium"
        >
          {t.doc_tab_individual}
        </button>
        <button
          onClick={() => setTab("worktree")}
          className="px-2 pb-2 text-sm text-recall-textMuted hover:text-recall-text"
        >
          {t.doc_tab_worktree}
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* 왼쪽 문서 목록 영역 */}
        <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium uppercase tracking-wide text-recall-textMuted">
              {t.doc_tab_individual}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => handleFileChange(e.target.files)}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="rounded-lg border border-recall-border px-2.5 py-1 text-sm hover:bg-white/5 disabled:opacity-50 transition"
            >
              {isUploading ? t.doc_uploading : t.doc_btn_upload || "업로드"}
            </button>
          </div>

          <div className="flex-1 space-y-1.5 overflow-y-auto custom-scrollbar">
            {visibleDocuments.map((doc) => {
              const isSelected = doc.id === activeDocId;
              const cat = doc.category_id ? categories.find((c) => c.id === doc.category_id) : null;
              return (
                <div
                  key={doc.id}
                  onClick={() => selectDocument(doc.id)}
                  className={`group relative flex w-full flex-col gap-0.5 rounded-lg border px-2.5 py-2 text-left transition cursor-pointer ${
                    isSelected
                      ? "border-recall-accent bg-recall-accent/10"
                      : "border-recall-border hover:bg-white/5"
                  }`}
                >
                  <span className="flex items-center gap-1.5 pr-12 text-sm font-medium">
                    {doc.status === "analyzing" && (
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-recall-accent" />
                    )}
                    {doc.status === "failed" && (
                      <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-danger" />
                    )}
                    <span className="truncate">{doc.name}</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] text-recall-textMuted">
                    {doc.status === "analyzing"
                      ? t.analyzing_msg || "AI 분석 중..."
                      : doc.status === "failed"
                      ? t.doc_status_failed_short
                      : "DOCUMENT"}
                    {cat && !cat.is_default && (
                      <CategoryBadge
                        name={cat.name}
                        color={getCategoryColor(categoryIndexById.get(cat.id) ?? 0)}
                      />
                    )}
                  </span>

                  <div className="absolute right-2 top-2 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    {doc.status === "failed" && retryDocument && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          retryDocument(doc.id);
                        }}
                        title={t.doc_reanalyze}
                        className="rounded p-1 text-recall-textMuted hover:text-recall-accent transition"
                      >
                        <RepeatIcon size={12} />
                      </button>
                    )}
                    {deleteDocument && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteDocument(doc.id);
                        }}
                        title={t.task_delete}
                        className="rounded p-1 text-recall-textMuted hover:text-recall-danger transition"
                      >
                        <TrashIcon size={12} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 오른쪽 상세 영역 */}
        {activeDoc ? (
          <div className="flex flex-1 flex-col p-4 overflow-hidden">
            {/* 상단 제목 및 버튼 */}
            <div className="mb-3 flex items-center justify-between pb-3 border-b border-recall-border/60">
              <div>
                <p className="text-base font-bold text-recall-text">{activeDoc.name}</p>
                <p className="text-xs text-recall-textMuted mt-0.5">DOCUMENT · {t.doc_meeting_reference_label}</p>
              </div>
              <div className="flex gap-1.5">
                {retryDocument && (
                  <button
                    onClick={() => retryDocument(activeDoc.id)}
                    className="rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
                  >
                    {t.doc_reanalyze}
                  </button>
                )}
              </div>
            </div>

            {/* 깔끔한 텍스트 탭: [정리된 내용] / [원본 파일] */}
            {isDocCompleted && (
              <div className="mb-3 flex gap-1 rounded-xl border border-recall-border bg-recall-bgSoft p-1 w-fit">
                <button
                  onClick={() => setDetailContentTab("summary")}
                  className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                    detailContentTab === "summary"
                      ? "bg-recall-accent text-white shadow-sm"
                      : "text-recall-textMuted hover:text-recall-text"
                  }`}
                >
                  {t.doc_tab_summary_view}
                </button>
                <button
                  onClick={() => setDetailContentTab("original")}
                  className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                    detailContentTab === "original"
                      ? "bg-recall-accent text-white shadow-sm"
                      : "text-recall-textMuted hover:text-recall-text"
                  }`}
                >
                  {t.doc_tab_original_view}
                </button>
              </div>
            )}

            {/* 본문 영역 */}
            {activeDoc.status === "analyzing" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-2">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                <p className="text-sm text-recall-textMuted">{t.analyzing_msg || "문서를 분석하는 중입니다..."}</p>
              </div>
            ) : activeDoc.status === "failed" ? (
              <div className="flex flex-1 items-center justify-center rounded-xl border border-recall-danger/30 bg-recall-danger/5">
                <p className="text-sm text-recall-danger">{t.doc_analysis_failed_msg}</p>
              </div>
            ) : detailContentTab === "summary" ? (
              /* [정리된 내용 탭] AI가 본문을 추출하고 요약/정리한 인사이트 화면 */
              <DocumentDetailPanel
                detail={activeDocDetail ?? null}
                figures={activeDocFigures ?? []}
                isLoading={!!isDetailLoading}
                t={t}
              />
            ) : (
              /* [원본 파일 탭] PDF / 이미지 등 업로드된 원본 문서 뷰어 */
              <div className="flex-1 overflow-hidden">
                <DocumentOriginalViewer
                  workspaceId={workspaceId}
                  documentId={activeDoc.id}
                  documentName={activeDoc.name}
                />
              </div>
            )}
          </div>
        ) : (
          /* 선택 안 됨 안내 영역 */
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="flex flex-1 flex-col items-center justify-center gap-2 m-6 rounded-2xl border-2 border-dashed border-recall-border/60 hover:border-recall-accent/60 bg-white/5 transition cursor-pointer"
          >
            <p className="text-base font-medium text-recall-text">
              {t.doc_not_selected || "문서를 선택하거나 여기에 드래그하여 업로드하세요"}
            </p>
            <p className="text-xs text-recall-textMuted">
              {t.doc_upload_hint}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}