import { useRef, useState } from "react";
import { AnalyzedDocument } from "../types";
import { formatDate } from "../hooks/useDocumentAnalysis";
import { DocumentIcon, UploadIcon, TrashIcon } from "./icons";

interface Props {
  documents: AnalyzedDocument[];
  activeDocumentId: string | null;
  uploadDocuments: (files: File[]) => void;
  removeDocument: (id: string) => void;
  selectDocument: (id: string | null) => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

// 왼쪽 문서 목록 - 업로드된 문서 전부, 분석 중이면 점 깜빡임
function DocumentList({
  documents,
  activeDocumentId,
  onSelect,
  onRemove,
}: {
  documents: AnalyzedDocument[];
  activeDocumentId: string | null;
  onSelect: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
        문서 목록
      </p>
      <div className="flex-1 space-y-1.5 overflow-y-auto">
        {documents.length === 0 ? (
          <p className="text-xs text-recall-textMuted">아직 업로드된 문서가 없어요.</p>
        ) : (
          documents.map((doc) => {
            const isSelected = doc.id === activeDocumentId;
            return (
              <div
                key={doc.id}
                onClick={() => onSelect(doc.id)}
                className={`group flex cursor-pointer items-start gap-2 rounded-lg border px-2.5 py-2 ${
                  isSelected
                    ? "border-recall-accent bg-recall-accent/10"
                    : "border-recall-border hover:bg-white/5"
                }`}
              >
                <DocumentIcon size={15} className="mt-0.5 flex-shrink-0 text-recall-textMuted" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    {doc.status === "analyzing" && (
                      <span className="h-1.5 w-1.5 flex-shrink-0 animate-pulse rounded-full bg-recall-accent" />
                    )}
                    <span className="truncate text-xs font-medium text-recall-text">{doc.name}</span>
                  </div>
                  <p className="text-[11px] text-recall-textMuted">
                    {formatFileSize(doc.size)} · {formatDate(doc.uploadedAt)}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove(doc.id);
                  }}
                  className="hidden flex-shrink-0 text-recall-textMuted hover:text-recall-danger group-hover:inline"
                  aria-label="삭제"
                >
                  <TrashIcon size={13} />
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

type DetailTab = "summary" | "keywords" | "original";

// 원본 미리보기 - pdf/이미지는 화면에 바로 보여주고, 그 외는 다운로드 링크만 제공
function OriginalPreview({ doc }: { doc: AnalyzedDocument }) {
  if (!doc.fileUrl) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 rounded-lg border border-recall-border">
        <p className="text-sm text-recall-textMuted">원본 미리보기를 불러올 수 없어요.</p>
      </div>
    );
  }
  if (doc.fileType === "application/pdf") {
    return <iframe src={doc.fileUrl} title={doc.name} className="h-full w-full rounded-lg border border-recall-border" />;
  }
  if (doc.fileType?.startsWith("image/")) {
    return (
      <div className="flex h-full items-center justify-center overflow-auto rounded-lg border border-recall-border p-3">
        <img src={doc.fileUrl} alt={doc.name} className="max-h-full max-w-full rounded" />
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 rounded-lg border border-recall-border">
      <p className="text-sm text-recall-textMuted">이 파일 형식은 미리보기를 지원하지 않아요.</p>
      <a
        href={doc.fileUrl}
        download={doc.name}
        className="rounded-lg border border-recall-border px-3 py-1.5 text-xs text-recall-text hover:bg-white/5"
      >
        다운로드
      </a>
    </div>
  );
}

// 오른쪽 상세 - 분석 중이면 로딩, 끝나면 요약/키워드/원본 탭
function DocumentDetail({ doc }: { doc: AnalyzedDocument }) {
  const [tab, setTab] = useState<DetailTab>("summary");

  return (
    <div className="flex h-full flex-1 flex-col p-4">
      <p className="mb-3 truncate text-sm font-medium text-recall-text">{doc.name}</p>

      {doc.status === "analyzing" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-recall-border">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
          <p className="text-sm text-recall-textMuted">문서 내용을 분석하는 중이에요...</p>
        </div>
      ) : (
        <>
          <div className="mb-3 flex gap-0.5 border-b border-recall-border">
            {(
              [
                { id: "summary", label: "요약" },
                { id: "keywords", label: "키워드" },
                { id: "original", label: "원본" },
              ] as const
            ).map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-2 py-1 text-xs ${
                  tab === t.id
                    ? "border-b-2 border-recall-accent text-recall-text"
                    : "text-recall-textMuted hover:text-recall-text"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto">
            {tab === "summary" && (
              <div className="rounded-lg border border-recall-border p-3">
                <p className="text-sm text-recall-text">{doc.summary}</p>
              </div>
            )}
            {tab === "keywords" && (
              <div className="rounded-lg border border-recall-border p-3">
                <div className="flex flex-wrap gap-1.5">
                  {doc.keywords?.map((kw) => (
                    <span
                      key={kw}
                      className="rounded-full border border-recall-border px-2.5 py-1 text-xs text-recall-text"
                    >
                      {kw}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {tab === "original" && (
              <div className="h-full min-h-[400px]">
                <OriginalPreview doc={doc} />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function DocumentAnalysisView({
  documents,
  activeDocumentId,
  uploadDocuments,
  removeDocument,
  selectDocument,
}: Props) {
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeDocument = documents.find((d) => d.id === activeDocumentId) ?? null;

  return (
    <div
      onDragEnter={(e) => {
        e.preventDefault();
        dragCounter.current += 1;
        setIsDragOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={(e) => {
        e.preventDefault();
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) setIsDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        dragCounter.current = 0;
        setIsDragOver(false);
        if (e.dataTransfer.files.length > 0) uploadDocuments(Array.from(e.dataTransfer.files));
      }}
      className="relative flex h-full w-full flex-col bg-recall-bgMain text-recall-text"
    >
      {isDragOver && (
        <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-2 bg-recall-bg/85 backdrop-blur-sm">
          <UploadIcon size={22} className="text-recall-accent" />
          <p className="text-base font-medium text-recall-text">파일을 올려두세요</p>
        </div>
      )}

      <div className="flex items-center justify-between border-b border-recall-border p-3">
        <p className="text-sm font-medium">문서 분석</p>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 rounded-lg border border-recall-border px-3 py-1.5 text-xs text-recall-text hover:bg-white/5"
        >
          <UploadIcon size={14} />
          문서 업로드
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              uploadDocuments(Array.from(e.target.files));
            }
            e.target.value = "";
          }}
        />
      </div>

      <div className="flex flex-1 overflow-hidden">
        <DocumentList
          documents={documents}
          activeDocumentId={activeDocumentId}
          onSelect={selectDocument}
          onRemove={removeDocument}
        />

        {activeDocument ? (
          <DocumentDetail doc={activeDocument} />
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-recall-textMuted">
              문서를 업로드하거나 왼쪽 목록에서 문서를 선택하세요.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}