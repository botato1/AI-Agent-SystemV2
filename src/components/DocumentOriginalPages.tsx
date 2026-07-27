import { DocumentChunk, DocumentFigure } from "../services/document";
import ContentBlocks from "./DocumentContentBlocks";
import FigureGallery from "./FigureGallery";

interface Props {
  chunks: DocumentChunk[];
  originalText: string | null;
  figures: DocumentFigure[];
}

// 원본을 페이지 단위로 묶어서, 해당 페이지에 표/차트/다이어그램/스캔 이미지가 있으면
// 그 페이지 텍스트 바로 위에 이미지를 같이 보여준다. (원본 = 이미지+텍스트가 같이 있는 문서 그 자체)
export default function DocumentOriginalPages({ chunks, originalText, figures }: Props) {
  const sortedChunks = [...chunks].sort((a, b) => a.chunk_index - b.chunk_index);

  if (sortedChunks.length === 0) {
    if (!originalText && figures.length === 0) return null;
    return (
      <div className="space-y-3">
        {figures.length > 0 && <FigureGallery figures={figures} />}
        {originalText && <ContentBlocks text={originalText} />}
      </div>
    );
  }

  const shownFigureIds = new Set<string>();

  return (
    <div className="space-y-3">
      {sortedChunks.map((chunk, i) => {
        const showPageLabel =
          chunk.page_number != null && (i === 0 || sortedChunks[i - 1].page_number !== chunk.page_number);
        const pageFigures = showPageLabel
          ? figures.filter((f) => f.page_number === chunk.page_number)
          : [];
        pageFigures.forEach((f) => shownFigureIds.add(f.figure_id));

        return (
          <div key={chunk.chunk_index} className="space-y-2">
            {showPageLabel && (
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-recall-textMuted/70">
                {chunk.page_number}페이지
              </p>
            )}
            {pageFigures.length > 0 && <FigureGallery figures={pageFigures} />}
            <ContentBlocks text={chunk.content} />
          </div>
        );
      })}

      {(() => {
        const leftover = figures.filter((f) => !shownFigureIds.has(f.figure_id));
        if (leftover.length === 0) return null;
        return (
          <div className="space-y-2">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-recall-textMuted/70">
              기타 이미지
            </p>
            <FigureGallery figures={leftover} />
          </div>
        );
      })()}
    </div>
  );
}
