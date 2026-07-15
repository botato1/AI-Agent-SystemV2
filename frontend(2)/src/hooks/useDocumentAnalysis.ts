import { useState } from "react";
import { AnalyzedDocument } from "../types";

interface WorkspaceDocState {
  documents: AnalyzedDocument[];
  activeDocumentId: string | null;
}

const EMPTY_STATE: WorkspaceDocState = { documents: [], activeDocumentId: null };

const DUMMY_SUMMARY =
  "이 문서는 API 게이트웨이 통합 방안과 세무사 대시보드 연동 시 고려해야 할 사항을 정리하고 있습니다. 인증 방식 통일과 응답 스키마 표준화가 핵심 논의 대상입니다.";

const DUMMY_KEYWORDS = ["API 게이트웨이", "인증 방식", "응답 스키마", "세무사 대시보드"];

function formatDate(ts: number): string {
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// workspaceId별로 문서 목록을 독립적으로 저장 - 워크스페이스를 바꿔도 서로 안 섞임
export function useDocumentAnalysis(workspaceId: string) {
  const [store, setStore] = useState<Record<string, WorkspaceDocState>>({});

  const current = store[workspaceId] ?? EMPTY_STATE;

  function updateState(updater: (prev: WorkspaceDocState) => WorkspaceDocState) {
    setStore((prev) => ({ ...prev, [workspaceId]: updater(prev[workspaceId] ?? EMPTY_STATE) }));
  }

  // 실제로는 업로드→분석에 시간이 걸리는 걸 흉내내기 위해 "분석 중" 상태를 잠깐 거침
  function uploadDocuments(files: File[]) {
    const newDocs: AnalyzedDocument[] = files.map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size,
      uploadedAt: Date.now(),
      status: "analyzing",
      summary: null,
      keywords: null,
      fileType: file.type,
      fileUrl: URL.createObjectURL(file), // 원본 미리보기/다운로드용 - 브라우저 메모리에만 존재 (새로고침하면 사라짐)
    }));

    updateState((prev) => ({
      documents: [...newDocs, ...prev.documents],
      activeDocumentId: newDocs.length > 0 ? newDocs[0].id : prev.activeDocumentId,
    }));

    newDocs.forEach((doc) => {
      setTimeout(() => {
        updateState((prev) => ({
          ...prev,
          documents: prev.documents.map((d) =>
            d.id === doc.id ? { ...d, status: "done", summary: DUMMY_SUMMARY, keywords: DUMMY_KEYWORDS } : d
          ),
        }));
      }, 1500 + Math.random() * 800);
    });
  }

  function removeDocument(id: string) {
    updateState((prev) => {
      const target = prev.documents.find((d) => d.id === id);
      if (target) URL.revokeObjectURL(target.fileUrl); // 메모리 누수 방지
      return {
        documents: prev.documents.filter((d) => d.id !== id),
        activeDocumentId: prev.activeDocumentId === id ? null : prev.activeDocumentId,
      };
    });
  }

  function selectDocument(id: string | null) {
    updateState((prev) => ({ ...prev, activeDocumentId: id }));
  }

  return {
    documents: current.documents,
    activeDocumentId: current.activeDocumentId,
    uploadDocuments,
    removeDocument,
    selectDocument,
  };
}

export { formatDate };