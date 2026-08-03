// src/components/DocumentOriginalViewer.tsx
import { useEffect, useState } from "react";
import { getDocumentFileApi } from "../services/document";
import { DownloadIcon, DocumentIcon } from "./icons";

interface Props {
  workspaceId: string;
  documentId: string;
  documentName: string;
}

export default function DocumentOriginalViewer({ workspaceId, documentId, documentName }: Props) {
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [contentType, setContentType] = useState<string>("");
  const [downloadFilename, setDownloadFilename] = useState<string>(documentName);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setErrorMsg(null);

    async function loadFile() {
      const res = await getDocumentFileApi(workspaceId, documentId);
      if (cancelled) return;

      if (res.status === "success" && res.blob) {
        const url = URL.createObjectURL(res.blob);
        setFileUrl(url);
        setContentType(res.contentType);
        if (res.filename) setDownloadFilename(res.filename);
      } else {
        setErrorMsg(res.message);
      }
      setIsLoading(false);
    }

    loadFile();

    return () => {
      cancelled = true;
      if (fileUrl) {
        URL.revokeObjectURL(fileUrl);
      }
    };
  }, [workspaceId, documentId]);

  function handleDownload() {
    if (!fileUrl) return;
    const a = document.createElement("a");
    a.href = fileUrl;
    a.download = downloadFilename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  if (isLoading) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 py-12 text-recall-textMuted">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
        <p className="text-sm">실제 원본 파일 불러오는 중...</p>
      </div>
    );
  }

  if (errorMsg || !fileUrl) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-recall-border bg-recall-bgMain p-6 text-center">
        <DocumentIcon size={28} className="text-recall-textMuted/60" />
        <p className="text-sm text-recall-textMuted">{errorMsg || "원본 파일 미리보기를 볼 수 없습니다."}</p>
      </div>
    );
  }

  const isImage = contentType.startsWith("image/");
  const isPdf = contentType.includes("pdf") || downloadFilename.toLowerCase().endsWith(".pdf");

  // PDF의 경우 툴바/네비게이션 패널을 숨기는 파라미터 추가
  const pdfViewUrl = isPdf ? `${fileUrl}#toolbar=0&navpanes=0` : fileUrl;

  return (
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-recall-border bg-black/20">
      {/* 상단 통합 헤더 (모든 파일 공통) */}
      <div className="flex items-center justify-between border-b border-recall-border bg-recall-bgSoft px-4 py-2.5 text-xs">
        <span className="truncate font-medium text-recall-text">
          {downloadFilename}
        </span>
        <button
          onClick={handleDownload}
          className="flex items-center gap-1.5 rounded-lg border border-recall-border bg-recall-bgMain px-3 py-1.5 text-recall-text hover:bg-white/5 transition flex-shrink-0 font-medium"
        >
          <DownloadIcon size={13} />
          <span>원본 다운로드</span>
        </button>
      </div>

      {/* 미리보기 본문 */}
      <div className="flex-1 overflow-auto p-2 flex items-center justify-center min-h-[380px]">
        {isImage ? (
          <img
            src={fileUrl}
            alt={downloadFilename}
            className="max-h-full max-w-full object-contain rounded shadow-sm"
          />
        ) : (
          /* PDF 및 문서 파일의 경우 브라우저 툴바 없이 깔끔하게 표시 */
          <iframe
            src={pdfViewUrl}
            title={downloadFilename}
            className="h-full w-full rounded border-0 bg-white"
          />
        )}
      </div>
    </div>
  );
}