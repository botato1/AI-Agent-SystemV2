import { useEffect, useRef, useState } from "react";
import { useWorktrees } from "../hooks/useWorktrees";
import { WorktreeStatus } from "../services/worktree";
import { Category } from "../services/category";
import { getCategoryColor } from "../utils/categoryColor";
import { UploadIcon, DocumentIcon, TrashIcon, ChevronLeftIcon } from "./icons";
import {
  DocumentDetail,
  DocumentFigure,
  getDocumentApi,
  getDocumentFiguresApi,
  retryDocumentApi,
} from "../services/document";
import DocumentDetailPanel from "./DocumentDetailPanel";
import DocumentOriginalViewer from "./DocumentOriginalViewer";
import CategoryBadge from "./CategoryBadge";

type PreviewContentTab = "summary" | "original";

function formatDate(iso?: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function statusBadge(t: any, status: WorktreeStatus) {
  switch (status) {
    case "pending":
    case "processing":
      return { label: t.worktree_status_pending, className: "bg-recall-accent/10 text-recall-accent" };
    case "completed":
      return { label: t.worktree_status_completed, className: "bg-emerald-500/10 text-emerald-400" };
    case "partially_completed":
      return { label: t.worktree_status_partial, className: "bg-amber-500/10 text-amber-400" };
    case "failed":
      return { label: t.worktree_status_failed, className: "bg-recall-danger/10 text-recall-danger" };
    default:
      return { label: status, className: "bg-recall-textMuted/10 text-recall-textMuted" };
  }
}

function analysisStatusLabel(t: any, status: string): string {
  switch (status) {
    case "pending":
      return t.worktree_file_status_pending;
    case "processing":
      return t.worktree_file_status_processing;
    case "completed":
      return t.worktree_file_status_completed;
    case "failed":
      return t.worktree_file_status_failed;
    case "excluded":
      return t.worktree_file_status_excluded;
    default:
      return status;
  }
}

export default function WorktreePanel({
  workspaceId,
  categories,
  selectedCategoryId,
  t,
}: {
  workspaceId: string;
  categories: Category[];
  selectedCategoryId: string | null;
  t: any;
}) {
  const categoryIndexById = new Map(categories.map((c, index) => [c.id, index]));
  const {
    worktrees: allWorktrees,
    isLoading,
    selectedWorktreeId,
    setSelectedWorktreeId,
    selectedWorktree,
    files,
    isFilesLoading,
    isUploading,
    uploadFolder,
    deleteWorktree,
    deleteFile,
  } = useWorktrees(workspaceId, selectedCategoryId);

  // 사이드바 전역 카테고리 선택기에서 고른 값 - null("전체")이면 전부, 아니면 그 카테고리만.
  const worktrees = selectedCategoryId
    ? allWorktrees.filter((w) => w.category_id === selectedCategoryId)
    : allWorktrees;

  const folderInputRef = useRef<HTMLInputElement>(null);
  const [previewFile, setPreviewFile] = useState<{ id: string; name: string } | null>(null);
  const [previewDetail, setPreviewDetail] = useState<DocumentDetail | null>(null);
  const [previewFigures, setPreviewFigures] = useState<DocumentFigure[]>([]);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [previewContentTab, setPreviewContentTab] = useState<PreviewContentTab>("summary");

  // webkitdirectory는 표준 React 타입에 없어서 ref로 직접 설정
  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute("webkitdirectory", "true");
      folderInputRef.current.setAttribute("directory", "true");
    }
  }, []);

  useEffect(() => {
    setPreviewContentTab("summary");

    if (!previewFile) {
      setPreviewDetail(null);
      setPreviewFigures([]);
      return;
    }
    let cancelled = false;

    loadPreviewDetail(previewFile.id, () => cancelled);

    return () => {
      cancelled = true;
    };
  }, [workspaceId, previewFile]);

  // 다른 워크트리를 선택하면 이전에 열어보던 파일 미리보기는 닫는다.
  useEffect(() => {
    setPreviewFile(null);
  }, [selectedWorktreeId]);

  async function loadPreviewDetail(fileId: string, isCancelled: () => boolean) {
    setIsPreviewLoading(true);
    const [detailRes, figuresRes] = await Promise.all([
      getDocumentApi(workspaceId, fileId),
      getDocumentFiguresApi(workspaceId, fileId),
    ]);
    if (!isCancelled()) {
      setPreviewDetail(detailRes.status === "success" ? detailRes.document : null);
      setPreviewFigures(figuresRes.status === "success" ? figuresRes.figures : []);
      setIsPreviewLoading(false);
    }
  }

  async function handleRetry() {
    if (!previewFile) return;
    setIsRetrying(true);
    const res = await retryDocumentApi(workspaceId, previewFile.id);
    setIsRetrying(false);

    if (res.status === "success") {
      await loadPreviewDetail(previewFile.id, () => false);
    } else {
      alert(`재분석 요청 실패: ${res.message}`);
    }
  }

  function handleFolderSelected(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;

    const fileArray = Array.from(fileList);
    const firstRelativePath = (fileArray[0] as any).webkitRelativePath || fileArray[0].name;
    const rootFolderName = firstRelativePath.split("/")[0] || t.worktree_default_folder_name;

    const entries = fileArray.map((file) => ({
      file,
      relativePath: (file as any).webkitRelativePath || file.name,
    }));

    uploadFolder(rootFolderName, entries);
  }

  return (
    <div className="flex h-full w-full bg-recall-bgMain text-recall-text">
      {/* 왼쪽 목록 */}
      <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
        <div className="mb-3 flex items-center justify-end">
          <input
            ref={folderInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              handleFolderSelected(e.target.files);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => folderInputRef.current?.click()}
            disabled={isUploading}
            className="flex items-center gap-1 rounded-lg border border-recall-border px-2.5 py-1 text-sm hover:bg-white/5 disabled:opacity-50"
          >
            <UploadIcon size={12} />
            {isUploading ? t.doc_uploading : t.worktree_upload_folder}
          </button>
        </div>

        <div className="flex-1 space-y-1.5 overflow-y-auto">
          {isLoading ? (
            <p className="text-sm text-recall-textMuted">{t.common_loading}</p>
          ) : worktrees.length === 0 ? (
            <p className="text-sm text-recall-textMuted">{t.worktree_no_folders}</p>
          ) : (
            worktrees.map((w) => {
              const isSelected = w.id === selectedWorktreeId;
              const badge = statusBadge(t, w.status);
              return (
                <div
                  key={w.id}
                  onClick={() => setSelectedWorktreeId(w.id)}
                  className={`group relative flex w-full flex-col gap-1 rounded-lg border px-2.5 py-2 text-left cursor-pointer ${
                    isSelected
                      ? "border-recall-accent bg-recall-accent/10"
                      : "border-recall-border hover:bg-white/5"
                  }`}
                >
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteWorktree(w.id);
                    }}
                    title={t.task_delete}
                    className="absolute right-2 top-2 rounded p-1 text-recall-textMuted opacity-0 transition-opacity hover:text-recall-danger group-hover:opacity-100"
                  >
                    <TrashIcon size={12} />
                  </button>
                  <span className="truncate pr-6 text-sm font-medium text-recall-text">{w.root_folder_name}</span>
                  <span className="flex items-center gap-1.5">
                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${badge.className}`}>
                      {badge.label}
                    </span>
                    <span className="text-xs text-recall-textMuted">{formatDate(w.created_at)}</span>
                  </span>
                  {(() => {
                    const cat = categories.find((c) => c.id === w.category_id);
                    if (!cat || cat.is_default) return null;
                    return (
                      <CategoryBadge
                        name={cat.name}
                        color={getCategoryColor(categoryIndexById.get(cat.id) ?? 0)}
                      />
                    );
                  })()}
                  <span className="text-xs text-recall-textMuted">
                    {t.worktree_file_count_label(w.completed_file_count, w.total_file_count)}
                    {w.failed_file_count > 0 ? t.worktree_failed_count_label(w.failed_file_count) : ""}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 오른쪽 상세 */}
      <div className="flex h-full flex-1 flex-col overflow-hidden p-4">
        {!selectedWorktree ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2">
            <UploadIcon size={24} className="text-recall-textMuted" />
            <p className="text-base text-recall-textMuted">
              {t.worktree_select_hint}
            </p>
          </div>
        ) : previewFile ? (
          <>
            <div className="mb-3 flex items-center justify-between">
              <button
                onClick={() => setPreviewFile(null)}
                className="flex items-center gap-1 text-sm text-recall-textMuted hover:text-recall-text"
              >
                <ChevronLeftIcon size={15} />
                {t.worktree_back_to_files}
              </button>
              <button
                onClick={handleRetry}
                disabled={isRetrying}
                className="rounded-lg border border-recall-border px-2.5 py-1.5 text-sm text-recall-text hover:bg-white/5 disabled:opacity-50"
              >
                {isRetrying ? t.worktree_reanalyzing : t.doc_reanalyze}
              </button>
            </div>
            <div className="mb-3">
              <p className="text-base font-medium text-recall-text">{previewFile.name}</p>
              <p className="text-sm text-recall-textMuted">CODE FOLDER · {selectedWorktree.root_folder_name}</p>
            </div>

            <div className="mb-3 flex gap-1 rounded-xl border border-recall-border bg-recall-bgSoft p-1 w-fit">
              <button
                onClick={() => setPreviewContentTab("summary")}
                className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                  previewContentTab === "summary"
                    ? "bg-recall-accent text-white shadow-sm"
                    : "text-recall-textMuted hover:text-recall-text"
                }`}
              >
                {t.doc_tab_summary_view}
              </button>
              <button
                onClick={() => setPreviewContentTab("original")}
                className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                  previewContentTab === "original"
                    ? "bg-recall-accent text-white shadow-sm"
                    : "text-recall-textMuted hover:text-recall-text"
                }`}
              >
                {t.doc_tab_original_view}
              </button>
            </div>

            {previewContentTab === "summary" ? (
              <DocumentDetailPanel detail={previewDetail} figures={previewFigures} isLoading={isPreviewLoading} t={t} />
            ) : (
              <div className="flex-1 overflow-hidden">
                <DocumentOriginalViewer
                  workspaceId={workspaceId}
                  documentId={previewFile.id}
                  documentName={previewFile.name}
                />
              </div>
            )}
          </>
        ) : (
          <>
            <div className="mb-3">
              <p className="text-base font-medium text-recall-text">{selectedWorktree.root_folder_name}</p>
              <p className="text-sm text-recall-textMuted">
                {statusBadge(t, selectedWorktree.status).label} · {t.worktree_total_files_label(selectedWorktree.total_file_count)} ·{" "}
                {formatDate(selectedWorktree.created_at)}
              </p>
            </div>

            <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border">
              {isFilesLoading ? (
                <p className="p-3 text-base text-recall-textMuted">{t.common_loading}</p>
              ) : files.length === 0 ? (
                <p className="p-3 text-base text-recall-textMuted">{t.worktree_no_files}</p>
              ) : (
                <div className="divide-y divide-recall-border">
                  {files.map((f) => (
                    <div key={f.id} className="group flex w-full items-center gap-2 px-3 py-2 hover:bg-white/5">
                      <button
                        onClick={() => setPreviewFile({ id: f.id, name: f.relative_path || f.original_filename })}
                        className="flex min-w-0 flex-1 items-center gap-2 text-left text-base"
                      >
                        <DocumentIcon size={13} className="flex-shrink-0 text-recall-textMuted" />
                        <span className="min-w-0 flex-1 truncate text-recall-text">
                          {f.relative_path || f.original_filename}
                        </span>
                        <span className="flex-shrink-0 text-sm text-recall-textMuted">
                          {formatFileSize(f.file_size_bytes)}
                        </span>
                        <span className="flex-shrink-0 rounded bg-recall-textMuted/10 px-1.5 py-0.5 text-[11px] text-recall-textMuted">
                          {analysisStatusLabel(t, f.analysis_status)}
                        </span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteFile(f.id);
                        }}
                        title={t.task_delete}
                        className="flex-shrink-0 rounded p-1 text-recall-textMuted opacity-0 transition-opacity hover:text-recall-danger group-hover:opacity-100"
                      >
                        <TrashIcon size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
