// src/hooks/useRecentMeetings.ts
import { useEffect, useState } from "react";
import { getRecentMeetingsApi, RecentMeetingItem } from "../services/meeting";

export function useRecentMeetings(workspaceId: string, limit: number = 4) {
  const [recentMeetings, setRecentMeetings] = useState<RecentMeetingItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  async function loadRecentMeetings() {
    if (!workspaceId) return;
    setIsLoading(true);
    const res = await getRecentMeetingsApi(workspaceId, limit);
    setIsLoading(false);

    if (res.status === "success") {
      setRecentMeetings(res.meetings);
      setTotalCount(res.total_count);
    }
  }

  useEffect(() => {
    loadRecentMeetings();
  }, [workspaceId, limit]);

  return {
    recentMeetings,
    totalCount,
    isLoading,
    reload: loadRecentMeetings,
  };
}