// src/hooks/useDocumentAnalysis.ts
import { useEffect, useRef, useState } from "react";
import { AnalyzedDocument } from "../types";
import {
  DocumentDetail,
  DocumentFigure,
  DocumentListItem,
  getDocumentListApi,
  uploadDocumentApi,
  getDocumentApi,
  getDocumentFiguresApi,
  deleteDocumentApi,
  retryDocumentApi,
  getDocumentStreamTicketApi,
} from "../services/document";

function toAnalyzedDocument(d: DocumentListItem): AnalyzedDocument {
  return {
    id: d.document_id,
    name: d.filename,
    size: 0,
    uploadedAt: new Date(d.created_at).getTime(),
    status: toDocStatus(d.analysis_status),
    summary: null,
    keywords: [],
    fileType: "",
    fileUrl: "",
    category_id: d.category_id ?? null,
  };
}

function toDocStatus(apiStatus: string): AnalyzedDocument["status"] {
  if (apiStatus === "completed") return "analyzed";
  if (apiStatus === "failed") return "failed";
  return "analyzing";
}

export function useDocumentAnalysis(workspaceId: string) {
  const [documents, setDocuments] = useState<AnalyzedDocument[]>([]);
  const [activeDocId, setActiveDocId] = useState<string | null>(null);
  const [activeDocDetail, setActiveDocDetail] = useState<DocumentDetail | null>(null);
  const [activeDocFigures, setActiveDocFigures] = useState<DocumentFigure[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDetailLoading, setIsDetailLoading] = useState(false);

  // 업로드 중이라 서버에 아직 문서 row가 없는(=클라이언트 임시 ID만 존재하는) 항목의
  // ID 집합. 백엔드는 처리(최대 5분)가 끝나야 row를 만들기 때문에, 그 사이 목록 폴링이
  // 이 항목들을 서버 응답으로 지워버리지 않도록 병합 시 보존한다.
  const pendingUploadIdsRef = useRef<Set<string>>(new Set());

  async function loadDocuments() {
    if (!workspaceId) return;
    const res = await getDocumentListApi(workspaceId);
    if (res.status === "success") {
      const serverDocs = res.documents.map(toAnalyzedDocument);
      const serverIds = new Set(serverDocs.map((d) => d.id));
      setDocuments((prev) => {
        const localOnly = prev.filter(
          (d) => pendingUploadIdsRef.current.has(d.id) && !serverIds.has(d.id)
        );
        return [...localOnly, ...serverDocs];
      });
    }
  }

  useEffect(() => {
    setActiveDocId(null);
    setIsLoading(true);
    loadDocuments().finally(() => setIsLoading(false));
  }, [workspaceId]);

  // 아직 분석 중인 문서가 있으면 완료될 때까지 목록을 주기적으로 재조회 -
  // WS로 못 받는 경우(연결 실패 등)에 대비한 안전망으로 계속 둔다.
  useEffect(() => {
    const hasPending = documents.some((d) => d.status === "analyzing");
    if (!hasPending) return;
    const timer = setInterval(loadDocuments, 5000);
    return () => clearInterval(timer);
  }, [documents, workspaceId]);

  // 워크스페이스 단위 실시간 문서 이벤트 - 다른 사용자의 업로드/삭제/분석완료가
  // 새로고침 없이 바로 반영되게 한다 (그래프뷰도 documents가 바뀌면 알아서 다시 그려짐).
  const docSocketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!workspaceId) return;

    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    async function connect() {
      const ticketRes = await getDocumentStreamTicketApi(workspaceId);
      if (cancelled || ticketRes.status !== "success" || !ticketRes.wsTicket) return;

      const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin;
      const wsBase = API_BASE_URL.replace(/^http/, "ws");
      const socket = new WebSocket(
        `${wsBase}/api/workspaces/${workspaceId}/documents/stream?ticket=${ticketRes.wsTicket}`
      );
      docSocketRef.current = socket;

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "document_added" || payload.type === "document_analysis_updated") {
            const incoming = toAnalyzedDocument(payload.document as DocumentListItem);
            setDocuments((prev) =>
              prev.some((d) => d.id === incoming.id)
                ? prev.map((d) => (d.id === incoming.id ? incoming : d))
                : [incoming, ...prev]
            );
          } else if (payload.type === "document_removed" && payload.document_id) {
            setDocuments((prev) => prev.filter((d) => d.id !== payload.document_id));
          }
        } catch (error) {
          console.error("document stream message parse error:", error);
        }
      };

      socket.onclose = (event) => {
        if (cancelled) return;
        if (event.code === 4401 || event.code === 4403) return;
        reconnectTimer = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      docSocketRef.current?.close();
      docSocketRef.current = null;
    };
  }, [workspaceId]);

  const activeDocStatus = documents.find((d) => d.id === activeDocId)?.status ?? null;

  useEffect(() => {
    async function loadDetail() {
      // 분석이 아직 안 끝났거나(임시 업로드 ID 포함) 실패한 문서는 상세/figures 데이터를
      // 화면에서 쓰지 않으므로 조회하지 않는다 - 임시 ID로 조회를 시도하면 서버에 없는
      // ID라 404만 남긴다.
      if (!workspaceId || !activeDocId || activeDocStatus !== "analyzed") {
        setActiveDocDetail(null);
        setActiveDocFigures([]);
        return;
      }
      setIsDetailLoading(true);
      const [detailRes, figuresRes] = await Promise.all([
        getDocumentApi(workspaceId, activeDocId),
        getDocumentFiguresApi(workspaceId, activeDocId),
      ]);
      setIsDetailLoading(false);
      setActiveDocDetail(detailRes.status === "success" ? detailRes.document : null);
      setActiveDocFigures(figuresRes.status === "success" ? figuresRes.figures : []);
    }

    loadDetail();
  }, [workspaceId, activeDocId, activeDocStatus]);

  async function uploadDocument(fileList: FileList | null, categoryId?: string) {
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
        category_id: categoryId ?? null,
      };
      setDocuments((prev) => [placeholder, ...prev]);
      setActiveDocId(tempId);
      pendingUploadIdsRef.current.add(tempId);

      const res = await uploadDocumentApi(workspaceId, file, undefined, undefined, categoryId);

      if (res.status === "success" && res.documentId) {
        pendingUploadIdsRef.current.delete(tempId);
        const newId = res.documentId as string;
        setDocuments((prev) => {
          // 업로드 응답을 기다리는 동안 폴링/WS가 먼저 서버 문서를 받아와 이미 목록에
          // 들어와 있을 수 있다 - 그 경우 placeholder를 같은 id로 또 붙이면(map) id가
          // 중복된 두 항목이 같이 렌더링된다. 이미 있으면 placeholder만 제거한다.
          if (prev.some((d) => d.id === newId)) {
            return prev.filter((d) => d.id !== tempId);
          }
          return prev.map((d) => (d.id === tempId ? { ...d, id: newId } : d));
        });
        setActiveDocId((prev) => (prev === tempId ? newId : prev));
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
      pendingUploadIdsRef.current.delete(id);
      setDocuments((prev) => prev.filter((d) => d.id !== id));
      setActiveDocId((prev) => (prev === id ? null : prev));
    } else {
      const detail = res.error && res.error !== "UNAUTHORIZED" ? `\n(${res.error})` : "";
      alert(`문서 삭제 실패: ${res.message}${detail}`);
    }
  }

  async function retryDocument(id: string) {
    setDocuments((prev) => prev.map((d) => (d.id === id ? { ...d, status: "analyzing" } : d)));
    const res = await retryDocumentApi(workspaceId, id);
    if (res.status === "success") {
      await loadDocuments();
      if (activeDocId === id) {
        const [detailRes, figuresRes] = await Promise.all([
          getDocumentApi(workspaceId, id),
          getDocumentFiguresApi(workspaceId, id),
        ]);
        setActiveDocDetail(detailRes.status === "success" ? detailRes.document : null);
        setActiveDocFigures(figuresRes.status === "success" ? figuresRes.figures : []);
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
    activeDocFigures,
    isLoading,
    isDetailLoading,
    uploadDocument,
    selectDocument,
    deleteDocument,
    retryDocument,
  };
}
