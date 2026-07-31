import { DocumentIcon } from "./icons";
import { DocumentDetail, DocumentFigure } from "../services/document";
import { cleanExtractedText } from "./DocumentContentBlocks";
import DocumentOriginalPages from "./DocumentOriginalPages";

interface DocumentDetailPanelProps {
  detail: DocumentDetail | null;
  figures: DocumentFigure[];
  isLoading: boolean;
  t: any;
}

// 문서 상세(원본 + 분석정보 + 이미지 + 요약) 그리드 — "개별 문서"와 워크트리 파일 미리보기가 공유한다.
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
      {/* 원본 패널 (메인, 2/3 폭) */}
      <div className="col-span-2 flex flex-col rounded-xl border border-recall-border bg-recall-bgSoft p-4 overflow-hidden">
        <p className="mb-2 text-sm font-medium uppercase tracking-wide text-recall-textMuted">
          {t.doc_tab_original}
        </p>
        {detail?.raw.original_text || detail?.raw.chunks?.length || figures.length ? (
          <div className="flex-1 space-y-2 overflow-y-auto text-sm leading-relaxed text-recall-textMuted">
            <DocumentOriginalPages
              chunks={detail?.raw.chunks ?? []}
              originalText={detail?.raw.original_text ?? null}
              figures={figures}
            />
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-recall-border bg-recall-bgMain p-4 text-center">
            <div>
              <DocumentIcon size={24} className="mx-auto mb-2 text-recall-textMuted" />
              <p className="text-sm text-recall-textMuted">{t.original_not_supported}</p>
            </div>
          </div>
        )}
      </div>

      {/* 분석 정보 / 이미지 / 요약 패널 (보조, 1/3 폭) */}
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

        <div className="max-h-48 flex-shrink-0 overflow-y-auto rounded-xl border border-recall-border bg-recall-bgSoft p-4">
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
