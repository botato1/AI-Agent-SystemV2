import { useEffect, useState } from "react";
import { WorkspaceDecision, getWorkspaceDecisionsApi } from "../services/decision";

// 워크스페이스 전체 기준 "현재 유효한" 결정사항 목록 (버전 히스토리 포함)
export function useWorkspaceDecisions(workspaceId: string) {
  const [decisions, setDecisions] = useState<WorkspaceDecision[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  async function load() {
    if (!workspaceId) return;
    const res = await getWorkspaceDecisionsApi(workspaceId, "active");
    if (res.status === "success") {
      setDecisions(res.decisions);
    }
  }

  useEffect(() => {
    setIsLoading(true);
    load().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  return { decisions, isLoading, refresh: load };
}
