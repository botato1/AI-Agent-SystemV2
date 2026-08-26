import { useEffect, useState } from "react";

// 문서 업로드 중인 워크스페이스 id 집합 - 컴포넌트 트리와 무관한 모듈 전역 상태로
// 관리한다 (lib/reanalyzeStatus.ts와 동일 패턴). DocumentAnalysisView가 다른 페이지로
// 이동했다 언마운트/재마운트돼도, 업로드 버튼이 다시 클릭 가능한 상태로 되돌아가서
// 같은 파일을 실수로 두 번 올리는 일이 없게 한다.
let uploadingWorkspaceIds = new Set<string>();
const listeners = new Set<(ids: Set<string>) => void>();

function emit() {
  listeners.forEach((listener) => listener(uploadingWorkspaceIds));
}

export function markUploadingDocument(workspaceId: string) {
  if (uploadingWorkspaceIds.has(workspaceId)) return;
  uploadingWorkspaceIds = new Set(uploadingWorkspaceIds).add(workspaceId);
  emit();
}

export function markUploadDocumentDone(workspaceId: string) {
  if (!uploadingWorkspaceIds.has(workspaceId)) return;
  const next = new Set(uploadingWorkspaceIds);
  next.delete(workspaceId);
  uploadingWorkspaceIds = next;
  emit();
}

export function useUploadingDocumentWorkspaceIds(): Set<string> {
  const [ids, setIds] = useState(uploadingWorkspaceIds);

  useEffect(() => {
    listeners.add(setIds);
    return () => {
      listeners.delete(setIds);
    };
  }, []);

  return ids;
}
