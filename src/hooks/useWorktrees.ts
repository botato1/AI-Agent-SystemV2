import { useEffect, useState } from "react";
import {
  Worktree,
  WorktreeFile,
  getWorktreeListApi,
  getWorktreeFilesApi,
  uploadWorktreeApi,
} from "../services/worktree";

const PENDING_STATUSES = new Set(["pending", "processing"]);

// 코드 폴더 업로드(워크트리) 실제 백엔드 연동
export function useWorktrees(workspaceId: string) {
  const [worktrees, setWorktrees] = useState<Worktree[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedWorktreeId, setSelectedWorktreeId] = useState<string | null>(null);
  const [files, setFiles] = useState<WorktreeFile[]>([]);
  const [isFilesLoading, setIsFilesLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const selectedWorktree = worktrees.find((w) => w.id === selectedWorktreeId) ?? null;

  async function loadWorktrees() {
    if (!workspaceId) return;
    const res = await getWorktreeListApi(workspaceId);
    if (res.status === "success") {
      setWorktrees(res.worktrees);
    }
  }

  useEffect(() => {
    setSelectedWorktreeId(null);
    setIsLoading(true);
    loadWorktrees().finally(() => setIsLoading(false));
  }, [workspaceId]);

  // 아직 처리 중인 워크트리가 있으면 완료될 때까지 목록을 주기적으로 재조회
  useEffect(() => {
    const hasPending = worktrees.some((w) => PENDING_STATUSES.has(w.status));
    if (!hasPending) return;
    const timer = setInterval(loadWorktrees, 5000);
    return () => clearInterval(timer);
  }, [worktrees, workspaceId]);

  useEffect(() => {
    async function loadFiles() {
      if (!workspaceId || !selectedWorktreeId) {
        setFiles([]);
        return;
      }
      setIsFilesLoading(true);
      const res = await getWorktreeFilesApi(workspaceId, selectedWorktreeId);
      setIsFilesLoading(false);
      setFiles(res.status === "success" ? res.files : []);
    }

    loadFiles();
  }, [workspaceId, selectedWorktreeId, selectedWorktree?.status]);

  async function uploadFolder(rootFolderName: string, entries: { file: File; relativePath: string }[]) {
    setIsUploading(true);
    const res = await uploadWorktreeApi(workspaceId, rootFolderName, entries);
    setIsUploading(false);

    if (res.status === "success" && res.worktree) {
      setWorktrees((prev) => [res.worktree as Worktree, ...prev]);
      setSelectedWorktreeId(res.worktree.id);
    } else {
      alert(`폴더 업로드 실패: ${res.message}`);
    }
  }

  return {
    worktrees,
    isLoading,
    selectedWorktreeId,
    setSelectedWorktreeId,
    selectedWorktree,
    files,
    isFilesLoading,
    isUploading,
    uploadFolder,
  };
}
