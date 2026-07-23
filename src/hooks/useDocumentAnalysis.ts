// src/hooks/useDocumentAnalysis.ts
import { useEffect, useState } from "react";
import { AnalyzedDocument } from "../types";
import {
  DocumentDetail,
  getDocumentListApi,
  uploadDocumentApi,
  getDocumentApi,
  deleteDocumentApi,
  retryDocumentApi,
} from "../services/document";

const PENDING_STATUSES = new Set(["pending", "processing"]);

function toDocStatus(apiStatus: string): AnalyzedDocument["status"] {
  if (apiStatus === "completed") return "analyzed";
  if (apiStatus === "failed") return "failed";
  return "analyzing";
}

export function useDocumentAnalysis(workspaceId: string) {
  const [documents, setDocuments] = useState<AnalyzedDocument[]>([]);
  const [activeDocId, setActiveDocId] = useState<string | null>(null);
  const [activeDocDetail, setActiveDocDetail] = useState<DocumentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);

  async function loadDocuments() {
    if (!workspaceId) return;
    const res = await getDocumentListApi(workspaceId);
    if (res.status === "success") {
      setDocuments(
        res.documents.map((d) => ({
          id: d.document_id,
          name: d.filename,
          size: 0,
          uploadedAt: new Date(d.created_at).getTime(),
          status: toDocStatus(d.analysis_status),
          summary: null,
          keywords: [],
          fileType: "",
          fileUrl: "",
        }))
      );
    }
  }

  useEffect(() => {
    setActiveDocId(null);
    setIsLoading(true);
    loadDocuments().finally(() => setIsLoading(false));
  }, [workspaceId]);

  // 아직 분석 중인 문서가 있으면 완료될 때까지 목록을 주기적으로 재조회
  useEffect(() => {
    const hasPending = documents.some((d) => d.status === "analyzing");
    if (!hasPending) return;
    const timer = setInterval(loadDocuments, 5000);
    return () => clearInterval(timer);
  }, [documents, workspaceId]);

  useEffect(() => {
    async function loadDetail() {
      if (!workspaceId || !activeDocId) {
        setActiveDocDetail(null);
        return;
      }
      setIsDetailLoading(true);
      const res = await getDocumentApi(workspaceId, activeDocId);
      setIsDetailLoading(false);
      setActiveDocDetail(res.status === "success" ? res.document : null);
    }

    loadDetail();
  }, [workspaceId, activeDocId]);

  async function uploadDocument(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) return;

    const files = Array.from(fileList);

    for (const file of files) {
      const tempId = crypto.randomUUID();
      const placeholder: AnalyzedDocument = {
        id: tempId,
        name: file.name,
        size: file.size,
        uploadedAt: Date.now(),
        status: "analyzing",
        summary: null,
        keywords: [],
        fileType: file.type || "application/octet-stream",
        fileUrl: "",
      };
      setDocuments((prev) => [placeholder, ...prev]);
      setActiveDocId(tempId);

      const res = await uploadDocumentApi(workspaceId, file);

      if (res.status === "success" && res.documentId) {
        setDocuments((prev) =>
          prev.map((d) => (d.id === tempId ? { ...d, id: res.documentId as string } : d))
        );
        setActiveDocId((prev) => (prev === tempId ? (res.documentId as string) : prev));
        await loadDocuments();
      } else {
        setDocuments((prev) => prev.map((d) => (d.id === tempId ? { ...d, status: "failed" } : d)));
        alert(`문서 업로드 실패: ${res.message}`);
      }
    }
  }

  async function deleteDocument(id: string) {
    const res = await deleteDocumentApi(workspaceId, id);
    if (res.status === "success") {
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      setActiveDocId((prev) => (prev === id ? null : prev));
    } else {
      alert(`문서 삭제 실패: ${res.message}`);
    }
  }

  async function retryDocument(id: string) {
    setDocuments((prev) => prev.map((d) => (d.id === id ? { ...d, status: "analyzing" } : d)));
    const res = await retryDocumentApi(workspaceId, id);
    if (res.status === "success") {
      await loadDocuments();
      if (activeDocId === id) {
        const detailRes = await getDocumentApi(workspaceId, id);
        setActiveDocDetail(detailRes.status === "success" ? detailRes.document : null);
      }
    } else {
      setDocuments((prev) => prev.map((d) => (d.id === id ? { ...d, status: "failed" } : d)));
      alert(`재분석 요청 실패: ${res.message}`);
    }
  }

  function selectDocument(id: string | null) {
    setActiveDocId(id);
  }

  return {
    documents,
    activeDocId,
    activeDocDetail,
    isLoading,
    isDetailLoading,
    uploadDocument,
    selectDocument,
    deleteDocument,
    retryDocument,
  };
}
