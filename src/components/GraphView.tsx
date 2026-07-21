// src/components/GraphView.tsx
import { AnalyzedDocument } from "../types"; // types.ts에서 안정적으로 가져옴
import { SparklesIcon } from "./icons";

interface GraphViewProps {
  documents: AnalyzedDocument[];
  onGoToAnalysis: (id: string) => void;
  t: any;
}

export default function GraphView({ documents, onGoToAnalysis, t }: GraphViewProps) {
  const analyzedDocs = documents.filter((d) => d.status === "analyzed");

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain p-4 text-recall-text">
      <div className="mb-4">
        <p className="text-sm font-medium">{t.graph_title}</p>
        <p className="text-xs text-recall-textMuted">{t.graph_sub}</p>
      </div>

      {analyzedDocs.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-recall-border bg-recall-bgSoft">
          <p className="text-sm text-recall-textMuted">{t.graph_no_docs}</p>
        </div>
      ) : (
        <div className="grid flex-1 grid-cols-3 gap-4 overflow-hidden">
          {/* 그래프 캔버스 구역 (임시 목록 뷰형태로 연동) */}
          <div className="col-span-2 flex flex-col rounded-xl border border-recall-border bg-recall-bgSoft p-4">
            <div className="flex-1 space-y-3 overflow-y-auto">
              {analyzedDocs.map((doc) => (
                <div
                  key={doc.id}
                  onClick={() => onGoToAnalysis(doc.id)}
                  className="group flex cursor-pointer items-center justify-between rounded-lg border border-recall-border bg-recall-bgMain p-3 hover:border-recall-accent"
                >
                  <div>
                    <p className="text-xs font-semibold">{doc.name}</p>
                    <p className="text-[10px] text-recall-textMuted">
                      {t.graph_connected_count}: {doc.keywords?.length || 0}
                      {t.graph_connected_suffix}
                    </p>
                  </div>
                  <button className="rounded bg-recall-accent/10 px-2.5 py-1 text-[11px] text-recall-accent group-hover:bg-recall-accent group-hover:text-white">
                    {t.graph_btn_view_analysis}
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* 정보 패널 */}
          <div className="flex flex-col gap-4">
            <div className="rounded-xl border border-recall-border bg-recall-bgSoft p-4">
              <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
                <SparklesIcon size={14} className="text-recall-accent" />
                {t.doc_tab_keywords} (Top 5)
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Array.from(new Set(analyzedDocs.flatMap((d) => d.keywords || [])))
                  .slice(0, 5)
                  .map((kw: string) => (
                    <span
                      key={kw}
                      className="rounded-full border border-recall-border bg-recall-bgMain px-2 py-1 text-[11px]"
                    >
                      {kw}
                    </span>
                  ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}