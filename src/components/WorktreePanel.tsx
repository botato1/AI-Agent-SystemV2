import { useEffect, useRef } from "react";
import { useWorktrees } from "../hooks/useWorktrees";
import { WorktreeStatus } from "../services/worktree";
import { UploadIcon, DocumentIcon } from "./icons";

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

function statusBadge(status: WorktreeStatus) {
  switch (status) {
    case "pending":
    case "processing":
      return { label: "처리 중", className: "bg-recall-accent/10 text-recall-accent" };
    case "completed":
      return { label: "완료", className: "bg-emerald-500/10 text-emerald-400" };
    case "partially_completed":
      return { label: "일부 실패", className: "bg-amber-500/10 text-amber-400" };
    case "failed":
      return { label: "실패", className: "bg-recall-danger/10 text-recall-danger" };
    default:
      return { label: status, className: "bg-recall-textMuted/10 text-recall-textMuted" };
  }
}

function analysisStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "대기";
    case "processing":
      return "분석 중";
    case "completed":
      return "완료";
    case "failed":
      return "실패";
    case "excluded":
      return "제외됨";
    default:
      return status;
  }
}

export default function WorktreePanel({ workspaceId }: { workspaceId: string }) {
  const {
    worktrees,
    isLoading,
    selectedWorktreeId,
    setSelectedWorktreeId,
    selectedWorktree,
    files,
    isFilesLoading,
    isUploading,
    uploadFolder,
  } = useWorktrees(workspaceId);

  const folderInputRef = useRef<HTMLInputElement>(null);

  // webkitdirectory는 표준 React 타입에 없어서 ref로 직접 설정
  useEffect(() => {
    if (folderInputRef.current) {
      folderInputRef.current.setAttribute("webkitdirectory", "true");
      folderInputRef.current.setAttribute("directory", "true");
    }
  }, []);

  function handleFolderSelected(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;

    const fileArray = Array.from(fileList);
    const firstRelativePath = (fileArray[0] as any).webkitRelativePath || fileArray[0].name;
    const rootFolderName = firstRelativePath.split("/")[0] || "업로드된 폴더";

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
        <div className="mb-3 flex items-center justify-between">
          <p className="text-sm font-medium uppercase tracking-wide text-recall-textMuted">워크트리</p>
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
            {isUploading ? "업로드 중..." : "폴더 업로드"}
          </button>
        </div>

        <div className="flex-1 space-y-1.5 overflow-y-auto">
          {isLoading ? (
            <p className="text-sm text-recall-textMuted">불러오는 중...</p>
          ) : worktrees.length === 0 ? (
            <p className="text-sm text-recall-textMuted">아직 업로드된 폴더가 없습니다.</p>
          ) : (
            worktrees.map((w) => {
              const isSelected = w.id === selectedWorktreeId;
              const badge = statusBadge(w.status);
              return (
                <button
                  key={w.id}
                  onClick={() => setSelectedWorktreeId(w.id)}
                  className={`flex w-full flex-col gap-1 rounded-lg border px-2.5 py-2 text-left ${
                    isSelected
                      ? "border-recall-accent bg-recall-accent/10"
                      : "border-recall-border hover:bg-white/5"
                  }`}
                >
                  <span className="truncate text-sm font-medium text-recall-text">{w.root_folder_name}</span>
                  <span className="flex items-center gap-1.5">
                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${badge.className}`}>
                      {badge.label}
                    </span>
                    <span className="text-xs text-recall-textMuted">{formatDate(w.created_at)}</span>
                  </span>
                  <span className="text-xs text-recall-textMuted">
                    파일 {w.completed_file_count}/{w.total_file_count}
                    {w.failed_file_count > 0 ? ` · 실패 ${w.failed_file_count}` : ""}
                  </span>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* 오른쪽 상세 */}
      <div className="flex h-full flex-1 flex-col p-4">
        {!selectedWorktree ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2">
            <UploadIcon size={24} className="text-recall-textMuted" />
            <p className="text-base text-recall-textMuted">
              왼쪽에서 폴더를 선택하거나, "폴더 업로드"로 코드 폴더를 올려보세요.
            </p>
          </div>
        ) : (
          <>
            <div className="mb-3">
              <p className="text-base font-medium text-recall-text">{selectedWorktree.root_folder_name}</p>
              <p className="text-sm text-recall-textMuted">
                {statusBadge(selectedWorktree.status).label} · 총 {selectedWorktree.total_file_count}개 파일 ·{" "}
                {formatDate(selectedWorktree.created_at)}
              </p>
            </div>

            <div className="flex-1 overflow-y-auto rounded-lg border border-recall-border">
              {isFilesLoading ? (
                <p className="p-3 text-base text-recall-textMuted">불러오는 중...</p>
              ) : files.length === 0 ? (
                <p className="p-3 text-base text-recall-textMuted">파일이 없습니다.</p>
              ) : (
                <div className="divide-y divide-recall-border">
                  {files.map((f) => (
                    <div key={f.id} className="flex items-center gap-2 px-3 py-2 text-base">
                      <DocumentIcon size={13} className="flex-shrink-0 text-recall-textMuted" />
                      <span className="min-w-0 flex-1 truncate text-recall-text">
                        {f.relative_path || f.original_filename}
                      </span>
                      <span className="flex-shrink-0 text-sm text-recall-textMuted">
                        {formatFileSize(f.file_size_bytes)}
                      </span>
                      <span className="flex-shrink-0 rounded bg-recall-textMuted/10 px-1.5 py-0.5 text-[11px] text-recall-textMuted">
                        {analysisStatusLabel(f.analysis_status)}
                      </span>
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
