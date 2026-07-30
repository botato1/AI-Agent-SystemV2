// src/components/DocumentDetailPanel.tsx
import { DocumentDetail, DocumentFigure } from "../services/document";
import { cleanExtractedText } from "./DocumentContentBlocks";
import DocumentOriginalViewer from "./DocumentOriginalViewer"; // 신규 추가

interface DocumentDetailPanelProps {
  detail: DocumentDetail | null;
  figures: DocumentFigure[];
  isLoading: boolean;
  t: any;
}

export default function DocumentDetailPanel({ detail, figures, isLoading, t }: DocumentDetailPanelProps) {
  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-base text-recall-textMuted">불러오는 중...</p>
      </div>
    );
  }

  return (
    <div className="grid flex-1 grid-cols-3 gap-4 overflow-hidden">
      {/* 💡 실제 업로드된 파일 바이너리 그대로 보여주는 원본 패널 (2/3 폭) */}
      <div className="col-span-2 flex flex-col rounded-xl border border-recall-border bg-recall-bgSoft p-4 overflow-hidden">
        <p className="mb-2 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
          {t.doc_tab_original}
        </p>
        {detail ? (
          <DocumentOriginalViewer
            workspaceId={detail.workspace_id}
            documentId={detail.document_id}
            documentName={detail.filename}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-recall-border bg-recall-bgMain p-4 text-center">
            <p className="text-sm text-recall-textMuted">{t.original_not_supported}</p>
          </div>
        )}
      </div>

      {/* 분석 정보 / 요약 패널 (1/3 폭) */}
      <div className="flex flex-col gap-4 overflow-hidden">
        <div className="rounded-xl border border-recall-border bg-recall-bgSoft p-4">
          <p className="mb-2 text-sm font-medium uppercase tracking-wide text-recall-textMuted">분석 정보</p>
          <div className="flex flex-wrap gap-1.5 text-sm text-recall-textMuted">
            <span className="rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1">
              페이지 {detail?.analysis.page_count ?? "-"}
            </span>
            <span className="rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1">
              표 {detail?.analysis.table_count ?? "-"}
            </span>
            <span className="rounded-full border border-recall-border bg-recall-bgMain px-2.5 py-1">
              차트 {detail?.analysis.graph_count ?? "-"}
            </span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto rounded-xl border border-recall-border bg-recall-bgSoft p-4">
          <p className="mb-2 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
            {t.doc_tab_summary}
          </p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">
            {detail?.analysis.summary ? cleanExtractedText(detail.analysis.summary) : "요약이 없습니다."}
          </p>
        </div>
      </div>
    </div>
  );
}