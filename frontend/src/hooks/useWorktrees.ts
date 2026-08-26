import { useEffect, useState } from "react";
import {
  Worktree,
  WorktreeFile,
  getWorktreeListApi,
  getWorktreeFilesApi,
  uploadWorktreeApi,
  deleteWorktreeApi,
  deleteWorktreeFileApi,
} from "../services/worktree";

// 코드 폴더 업로드(워크트리) 실제 백엔드 연동
export function useWorktrees(workspaceId: string, selectedCategoryId?: string | null) {
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

  // 사이드바 카테고리 전환 시, 다른 카테고리 워크트리를 계속 열어둔 채로 보여주지 않게 초기화.
  useEffect(() => {
    setSelectedWorktreeId(null);
  }, [selectedCategoryId]);

  // 목록을 주기적으로 재조회 - 다른 팀원이 새로 올린 워크트리는 내 로컬 목록에 아직 없어서
  // "처리 중인 게 있을 때만" 폴링하는 조건으로는 못 잡는다(새로고침해야만 보이던 원인).
  useEffect(() => {
    if (!workspaceId) return;
    const timer = setInterval(loadWorktrees, 5000);
    return () => clearInterval(timer);
  }, [workspaceId]);

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

  async function deleteFile(fileId: string) {
    if (!selectedWorktreeId) return;
    const res = await deleteWorktreeFileApi(workspaceId, selectedWorktreeId, fileId);
    if (res.status === "success") {
      setFiles((prev) => prev.filter((f) => f.id !== fileId));
      if (res.worktree) {
        const updated = res.worktree;
        setWorktrees((prev) => prev.map((w) => (w.id === updated.id ? updated : w)));
      }
    } else {
      alert(`파일 삭제 실패: ${res.message}`);
    }
  }

  async function deleteWorktree(worktreeId: string) {
    const res = await deleteWorktreeApi(workspaceId, worktreeId);
    if (res.status === "success") {
      setWorktrees((prev) => prev.filter((w) => w.id !== worktreeId));
      setSelectedWorktreeId((prev) => (prev === worktreeId ? null : prev));
      if (res.failedFileCount > 0) {
        alert(`워크트리는 삭제됐지만 파일 ${res.failedFileCount}개는 정리에 실패했어요.`);
      }
    } else {
      alert(`워크트리 삭제 실패: ${res.message}`);
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
    deleteWorktree,
    deleteFile,
  };
}
