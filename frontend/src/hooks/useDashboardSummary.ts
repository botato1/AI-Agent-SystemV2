// src/hooks/useDashboardSummary.ts
import { useEffect, useState } from "react";
import { getDashboardSummaryApi, DashboardSummaryResponse } from "../services/dashboard";

export function useDashboardSummary(workspaceId: string) {
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  async function loadSummary() {
    if (!workspaceId) return;
    setIsLoading(true);
    const res = await getDashboardSummaryApi(workspaceId);
    setIsLoading(false);

    if (res.status === "success") {
      setSummary(res);
    }
  }

  useEffect(() => {
    loadSummary();
  }, [workspaceId]);

  return { summary, isLoading, reload: loadSummary };
}