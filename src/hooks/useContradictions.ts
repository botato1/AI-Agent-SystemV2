import { useEffect, useState } from "react";
import {
  Contradiction,
  ContradictionStatus,
  ContradictionResolutionType,
  ChangeSummaryDraft,
  getContradictionListApi,
  resolveContradictionApi,
  dismissContradictionApi,
  getChangeSummaryApi,
} from "../services/contradiction";

const CHANGE_SUMMARY_POLL_INTERVAL_MS = 2000;

// 워크스페이스 모순 감지 목록 + 해결/무시 처리 실제 백엔드 연동
export function useContradictions(workspaceId: string) {
  const [statusFilter, setStatusFilter] = useState<ContradictionStatus>("unresolved");
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // "반영"(change_acknowledged) 처리 직후의 대상 스냅샷. resolve()가 성공하면 목록에서는
  // 바로 빠지므로(더 이상 unresolved가 아니라서), 변경 요약을 보여주려면 따로 들고 있어야 한다.
  const [pendingSummaryFor, setPendingSummaryFor] = useState<Contradiction | null>(null);
  const [changeSummary, setChangeSummary] = useState<ChangeSummaryDraft | null>(null);
  const [isChangeSummaryLoading, setIsChangeSummaryLoading] = useState(false);

  async function loadList() {
    if (!workspaceId) return;
    const res = await getContradictionListApi(workspaceId, statusFilter);
    if (res.status === "success") {
      setContradictions(res.contradictions);
    }
  }

  useEffect(() => {
    setIsLoading(true);
    loadList().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, statusFilter]);

  // 새로 감지된 모순을 반영하기 위해 백그라운드에서 주기적으로 조용히 재조회 (로딩 스피너 없이)
  useEffect(() => {
    if (!workspaceId) return;
    const timer = setInterval(loadList, 8000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, statusFilter]);

  // 변경 요약은 백엔드에서 LLM으로 백그라운드 생성되므로(pending → completed/failed),
  // 완료될 때까지 일정 간격으로 폴링한다.
  useEffect(() => {
    if (!workspaceId || !pendingSummaryFor) {
      setChangeSummary(null);
      setIsChangeSummaryLoading(false);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    setIsChangeSummaryLoading(true);
    setChangeSummary(null);

    async function poll() {
      const res = await getChangeSummaryApi(workspaceId, pendingSummaryFor!.id);
      if (cancelled) return;

      if (res.status === "success" && res.changeSummary) {
        setChangeSummary(res.changeSummary);
        const done =
          res.changeSummary.generation_status === "completed" ||
          res.changeSummary.generation_status === "failed";
        if (done) {
          setIsChangeSummaryLoading(false);
          return;
        }
      }
      timer = setTimeout(poll, CHANGE_SUMMARY_POLL_INTERVAL_MS);
    }

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [workspaceId, pendingSummaryFor]);

  async function resolve(id: string, resolutionType: ContradictionResolutionType, note?: string) {
    const target = contradictions.find((c) => c.id === id) ?? null;
    const res = await resolveContradictionApi(workspaceId, id, resolutionType, note);
    if (res.status === "success") {
      setContradictions((prev) => prev.filter((c) => c.id !== id));
      if (resolutionType === "change_acknowledged" && target) {
        setPendingSummaryFor(target);
      }
    } else {
      alert(res.message);
    }
  }

  async function dismiss(id: string, note?: string) {
    const res = await dismissContradictionApi(workspaceId, id, note);
    if (res.status === "success") {
      setContradictions((prev) => prev.filter((c) => c.id !== id));
    } else {
      alert(res.message);
    }
  }

  function closeChangeSummary() {
    setPendingSummaryFor(null);
  }

  return {
    statusFilter,
    setStatusFilter,
    contradictions,
    isLoading,
    pendingSummaryFor,
    changeSummary,
    isChangeSummaryLoading,
    closeChangeSummary,
    resolve,
    dismiss,
    refresh: loadList,
  };
}
