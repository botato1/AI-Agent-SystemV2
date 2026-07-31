// src/components/DocumentAnalysisView.tsx
import { useRef, useState } from "react";
import { AnalyzedDocument } from "../types";
import { DocumentDetail, DocumentFigure } from "../services/document";
import WorktreePanel from "./WorktreePanel";
import DocumentDetailPanel from "./DocumentDetailPanel";
import DocumentOriginalViewer from "./DocumentOriginalViewer";

type AnalysisTab = "document" | "worktree";
type DetailContentTab = "summary" | "original";

interface DocumentAnalysisViewProps {
  workspaceId: string;
  documents: AnalyzedDocument[];
  activeDocId: string | null;
  activeDocDetail?: DocumentDetail | null;
  activeDocFigures?: DocumentFigure[];
  isDetailLoading?: boolean;
  uploadDocument: (fileList: FileList | null) => Promise<void> | void;
  selectDocument: (id: string | null) => void;
  deleteDocument?: (id: string) => void;
  retryDocument?: (id: string) => void;
  t: any;
}

export default function DocumentAnalysisView({
  workspaceId,
  documents,
  activeDocId,
  activeDocDetail,
  activeDocFigures,
  isDetailLoading,
  uploadDocument,
  selectDocument,
  deleteDocument,
  retryDocument,
  t,
}: DocumentAnalysisViewProps) {
  const activeDoc = documents.find((d) => d.id === activeDocId) ?? null;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<AnalysisTab>("document");
  
  // 요약 정리 vs 원본 파일 보기 탭
  const [detailContentTab, setDetailContentTab] = useState<DetailContentTab>("summary");

  const [isUploading, setIsUploading] = useState(false);
  const [uploadingFileName, setUploadingFileName] = useState("");

  const handleFileChange = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;

    setIsUploading(true);
    setUploadingFileName(fileList[0].name);

    try {
      await uploadDocument(fileList);
    } catch (error) {
      console.error("파일 업로드 오류:", error);
    } finally {
      setIsUploading(false);
      setUploadingFileName("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileChange(e.dataTransfer.files);
    }
  };

  if (tab === "worktree") {
    return (
      <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
        <div className="flex gap-0.5 border-b border-recall-border p-3 pb-0">
          <button
            onClick={() => setTab("document")}
            className="px-2 pb-2 text-sm text-recall-textMuted hover:text-recall-text"
          >
            개별 문서
          </button>
          <button
            onClick={() => setTab("worktree")}
            className="border-b-2 border-recall-accent px-2 pb-2 text-sm text-recall-accent font-medium"
          >
            코드 폴더
          </button>
        </div>
        <div className="flex flex-1 overflow-hidden">
          <WorktreePanel workspaceId={workspaceId} t={t} />
        </div>
      </div>
    );
  }

  const isDocCompleted = activeDoc && activeDoc.status !== "analyzing" && activeDoc.status !== "failed";

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
      {/* 상단 탭 navigation */}
      <div className="flex gap-0.5 border-b border-recall-border p-3 pb-0">
        <button
          onClick={() => setTab("document")}
          className="border-b-2 border-recall-accent px-2 pb-2 text-sm text-recall-accent font-medium"
        >
          개별 문서
        </button>
        <button
          onClick={() => setTab("worktree")}
          className="px-2 pb-2 text-sm text-recall-textMuted hover:text-recall-text"
        >
          코드 폴더
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* 왼쪽 문서 목록 영역 */}
        <div className="flex h-full w-64 flex-shrink-0 flex-col border-r border-recall-border p-3">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium uppercase tracking-wide text-recall-textMuted">
              {t.doc_list_title || "회의 자료"}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => handleFileChange(e.target.files)}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="rounded-lg border border-recall-border px-2.5 py-1 text-sm hover:bg-white/5 disabled:opacity-50 transition"
            >
              {isUploading ? "업로드 중..." : t.doc_btn_upload || "업로드"}
            </button>
          </div>

          <div className="flex-1 space-y-1.5 overflow-y-auto custom-scrollbar">
            {isUploading && (
              <div className="flex w-full flex-col gap-1 rounded-lg border border-recall-accent/50 bg-recall-accent/5 p-2.5 animate-pulse">
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 animate-spin rounded-full border-2 border-recall-accent border-t-transparent shrink-0" />
                  <span className="truncate text-sm font-medium text-recall-accent">
                    {uploadingFileName || "파일 업로드 중..."}
                  </span>
                </div>
                <span className="text-[11px] text-recall-textMuted pl-5">
                  서버로 전송하는 중입니다...
                </span>
              </div>
            )}

            {documents.map((doc) => {
              const isSelected = doc.id === activeDocId;
              return (
                <button
                  key={doc.id}
                  onClick={() => selectDocument(doc.id)}
                  className={`flex w-full flex-col gap-0.5 rounded-lg border px-2.5 py-2 text-left transition ${
                    isSelected
                      ? "border-recall-accent bg-recall-accent/10"
                      : "border-recall-border hover:bg-white/5"
                  }`}
                >
                  <span className="flex items-center gap-1.5 text-sm font-medium">
                    {doc.status === "analyzing" && (
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-recall-accent" />
                    )}
                    {doc.status === "failed" && (
                      <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-recall-danger" />
                    )}
                    <span className="truncate">{doc.name}</span>
                  </span>
                  <span className="text-[11px] text-recall-textMuted">
                    {doc.status === "analyzing"
                      ? t.analyzing_msg || "AI 분석 중..."
                      : doc.status === "failed"
                      ? "분석 실패"
                      : "DOCUMENT"}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 오른쪽 상세 영역 */}
        {activeDoc ? (
          <div className="flex flex-1 flex-col p-4 overflow-hidden">
            {/* 상단 제목 및 버튼 */}
            <div className="mb-3 flex items-center justify-between pb-3 border-b border-recall-border/60">
              <div>
                <p className="text-base font-bold text-recall-text">{activeDoc.name}</p>
                <p className="text-xs text-recall-textMuted mt-0.5">DOCUMENT · 회의 참조 자료</p>
              </div>
              <div className="flex gap-1.5">
                {activeDoc.status === "failed" && retryDocument && (
                  <button
                    onClick={() => retryDocument(activeDoc.id)}
                    className="rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-text hover:bg-white/5"
                  >
                    재분석
                  </button>
                )}
                {deleteDocument && (
                  <button
                    onClick={() => deleteDocument(activeDoc.id)}
                    className="rounded-lg border border-recall-border px-2.5 py-1.5 text-xs text-recall-textMuted hover:border-recall-danger hover:text-recall-danger transition"
                  >
                    삭제
                  </button>
                )}
              </div>
            </div>

            {/* 깔끔한 텍스트 탭: [정리된 내용] / [원본 파일] */}
            {isDocCompleted && (
              <div className="mb-3 flex gap-1 rounded-xl border border-recall-border bg-recall-bgSoft p-1 w-fit">
                <button
                  onClick={() => setDetailContentTab("summary")}
                  className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                    detailContentTab === "summary"
                      ? "bg-recall-accent text-white shadow-sm"
                      : "text-recall-textMuted hover:text-recall-text"
                  }`}
                >
                  정리된 내용
                </button>
                <button
                  onClick={() => setDetailContentTab("original")}
                  className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                    detailContentTab === "original"
                      ? "bg-recall-accent text-white shadow-sm"
                      : "text-recall-textMuted hover:text-recall-text"
                  }`}
                >
                  원본 파일
                </button>
              </div>
            )}

            {/* 본문 영역 */}
            {activeDoc.status === "analyzing" ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-2">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                <p className="text-sm text-recall-textMuted">{t.analyzing_msg || "문서를 분석하는 중입니다..."}</p>
              </div>
            ) : activeDoc.status === "failed" ? (
              <div className="flex flex-1 items-center justify-center rounded-xl border border-recall-danger/30 bg-recall-danger/5">
                <p className="text-sm text-recall-danger">문서 분석에 실패했습니다.</p>
              </div>
            ) : detailContentTab === "summary" ? (
              /* [정리된 내용 탭] AI가 본문을 추출하고 요약/정리한 인사이트 화면 */
              <DocumentDetailPanel
                detail={activeDocDetail ?? null}
                figures={activeDocFigures ?? []}
                isLoading={!!isDetailLoading}
                t={t}
              />
            ) : (
              /* [원본 파일 탭] PDF / 이미지 등 업로드된 원본 문서 뷰어 */
              <div className="flex-1 overflow-hidden">
                <DocumentOriginalViewer
                  workspaceId={workspaceId}
                  documentId={activeDoc.id}
                  documentName={activeDoc.name}
                />
              </div>
            )}
          </div>
        ) : (
          /* 선택 안 됨 안내 영역 */
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="flex flex-1 flex-col items-center justify-center gap-2 m-6 rounded-2xl border-2 border-dashed border-recall-border/60 hover:border-recall-accent/60 bg-white/5 transition cursor-pointer"
          >
            <p className="text-base font-medium text-recall-text">
              {t.doc_not_selected || "문서를 선택하거나 여기에 드래그하여 업로드하세요"}
            </p>
            <p className="text-xs text-recall-textMuted">
              PDF, Word, TXT 등의 회의 자료를 업로드하면 AI가 사전 분석을 진행합니다.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}