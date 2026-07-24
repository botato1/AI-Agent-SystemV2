import { useEffect, useState } from "react";
import { DocumentListItem, getDocumentListApi } from "../services/document";
import { CloseIcon, DocumentIcon } from "./icons";

interface LinkExistingDocumentModalProps {
  workspaceId: string;
  excludeIds: string[];
  onClose: () => void;
  onLink: (documentId: string) => Promise<boolean>;
}

export default function LinkExistingDocumentModal({
  workspaceId,
  excludeIds,
  onClose,
  onLink,
}: LinkExistingDocumentModalProps) {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [linkingId, setLinkingId] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      const res = await getDocumentListApi(workspaceId);
      setIsLoading(false);
      if (res.status === "success") setDocuments(res.documents);
    }
    load();
  }, [workspaceId]);

  const availableDocs = documents.filter((d) => !excludeIds.includes(d.document_id));

  async function handleLink(documentId: string) {
    setLinkingId(documentId);
    const ok = await onLink(documentId);
    setLinkingId(null);
    if (ok) onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between border-b border-recall-border pb-3">
          <p className="text-base font-semibold">기존 문서 연결</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        {isLoading ? (
          <p className="text-base text-recall-textMuted">불러오는 중...</p>
        ) : availableDocs.length === 0 ? (
          <p className="text-base text-recall-textMuted">
            연결할 수 있는 문서가 없습니다. "문서 분석"에서 먼저 업로드해 보세요.
          </p>
        ) : (
          <div className="max-h-80 space-y-1.5 overflow-y-auto">
            {availableDocs.map((doc) => (
              <div
                key={doc.document_id}
                className="flex items-center justify-between rounded-lg border border-recall-border px-3 py-2 text-sm"
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <DocumentIcon size={13} className="flex-shrink-0 text-recall-textMuted" />
                  <span className="truncate text-recall-text">{doc.filename}</span>
                </span>
                <button
                  onClick={() => handleLink(doc.document_id)}
                  disabled={linkingId === doc.document_id}
                  className="flex-shrink-0 rounded-lg bg-recall-accent/15 px-2.5 py-1 text-xs font-semibold text-recall-accent hover:bg-recall-accent hover:text-white disabled:opacity-50"
                >
                  {linkingId === doc.document_id ? "연결 중..." : "연결"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
