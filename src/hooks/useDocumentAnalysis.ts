// src/hooks/useDocumentAnalysis.ts
import { useState } from "react";
import { AnalyzedDocument } from "../types"; // 전역 types.ts 타입을 가져옵니다 (가져오기 선언 충돌 해결!)

interface WorkspaceDocState {
  documents: AnalyzedDocument[];
  activeDocId: string | null;
}

const EMPTY_STATE: WorkspaceDocState = { documents: [], activeDocId: null };

export function useDocumentAnalysis(workspaceId: string) {
  const [store, setStore] = useState<Record<string, WorkspaceDocState>>({});

  const current = store[workspaceId] ?? EMPTY_STATE;

  function updateState(updater: (prev: WorkspaceDocState) => WorkspaceDocState) {
    setStore((prev) => ({ ...prev, [workspaceId]: updater(prev[workspaceId] ?? EMPTY_STATE) }));
  }

  function uploadDocument(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;

    const newDocs: AnalyzedDocument[] = Array.from(fileList).map((file) => {
      const id = crypto.randomUUID();
      
      // 파일 업로드 직후는 analyzing 상태로 시작
      const doc: AnalyzedDocument = {
        id,
        name: file.name,
        size: file.size,
        uploadedAt: Date.now(),
        status: "analyzing",
        summary: null,
        keywords: null,
        fileType: file.type || "application/octet-stream",
        fileUrl: URL.createObjectURL(file),
      };

      // 1.8초 후 "done"이 아닌 완벽히 동기화된 "analyzed" 상태로 전환 처리
      setTimeout(() => {
        updateState((prev) => ({
          ...prev,
          documents: prev.documents.map((d) =>
            d.id === id
              ? {
                  ...d,
                  status: "analyzed", // "done" 대신 "analyzed"로 정확히 상태 일치!
                  summary: "이 문서는 프로젝트의 핵심 아키텍처 가이드라인을 정의합니다. 구성 요소 간 중복을 방지하고 일관된 흐름을 유지하는 것을 목표로 합니다.",
                  keywords: ["아키텍처", "가이드라인", "컴포넌트"],
                }
              : d
          ),
        }));
      }, 1800);

      return doc;
    });

    updateState((prev) => ({
      ...prev,
      documents: [...newDocs, ...prev.documents],
      activeDocId: newDocs[0].id,
    }));
  }

  function selectDocument(id: string | null) {
    updateState((prev) => ({ ...prev, activeDocId: id }));
  }

  // 뷰 컴포넌트(Props)가 요구하는 프로퍼티 명칭과 완벽히 매핑시켜 리턴합니다.
  return {
    documents: current.documents,
    activeDocId: current.activeDocId,
    uploadDocument,
    selectDocument,
  };
}