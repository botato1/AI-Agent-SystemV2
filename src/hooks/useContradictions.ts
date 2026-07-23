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

// 워크스페이스 모순 감지 목록 + 해결/무시 처리 실제 백엔드 연동
export function useContradictions(workspaceId: string) {
  const [statusFilter, setStatusFilter] = useState<ContradictionStatus>("unresolved");
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [changeSummary, setChangeSummary] = useState<ChangeSummaryDraft | null>(null);
  const [isChangeSummaryLoading, setIsChangeSummaryLoading] = useState(false);

  const selected = contradictions.find((c) => c.id === selectedId) ?? null;

  async function loadList() {
    if (!workspaceId) return;
    const res = await getContradictionListApi(workspaceId, statusFilter);
    if (res.status === "success") {
      setContradictions(res.contradictions);
    }
  }

  useEffect(() => {
    setSelectedId(null);
    setIsLoading(true);
    loadList().finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, statusFilter]);

  useEffect(() => {
    async function loadChangeSummary() {
      if (!workspaceId || !selected || selected.status !== "resolved") {
        setChangeSummary(null);
        return;
      }
      setIsChangeSummaryLoading(true);
      const res = await getChangeSummaryApi(workspaceId, selected.id);
      setIsChangeSummaryLoading(false);
      setChangeSummary(res.status === "success" ? res.changeSummary : null);
    }

    loadChangeSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, selectedId]);

  async function resolve(id: string, resolutionType: ContradictionResolutionType, note?: string) {
    const res = await resolveContradictionApi(workspaceId, id, resolutionType, note);
    if (res.status === "success") {
      setContradictions((prev) => prev.filter((c) => c.id !== id));
      setSelectedId((prev) => (prev === id ? null : prev));
    } else {
      alert(res.message);
    }
  }

  async function dismiss(id: string, note?: string) {
    const res = await dismissContradictionApi(workspaceId, id, note);
    if (res.status === "success") {
      setContradictions((prev) => prev.filter((c) => c.id !== id));
      setSelectedId((prev) => (prev === id ? null : prev));
    } else {
      alert(res.message);
    }
  }

  return {
    statusFilter,
    setStatusFilter,
    contradictions,
    isLoading,
    selectedId,
    setSelectedId,
    selected,
    changeSummary,
    isChangeSummaryLoading,
    resolve,
    dismiss,
  };
}
