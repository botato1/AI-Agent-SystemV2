import { DocumentFigure, resolveFigureUrl } from "../services/document";

const TYPE_LABEL: Record<DocumentFigure["type"], string> = {
  table: "표",
  chart: "차트",
  diagram: "다이어그램",
  image: "이미지",
};

export default function FigureGallery({
  figures,
  columns = 2,
}: {
  figures: DocumentFigure[];
  columns?: 1 | 2;
}) {
  if (figures.length === 0) return null;

  return (
    <div className={`grid gap-3 ${columns === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
      {figures.map((fig) => (
        <div
          key={fig.figure_id}
          className="overflow-hidden rounded-lg border border-recall-border bg-recall-bgMain"
        >
          <img
            src={resolveFigureUrl(fig.image_url)}
            alt={`${TYPE_LABEL[fig.type]} - ${fig.page_number}페이지`}
            loading="lazy"
            className="w-full object-contain"
          />
          <p className="px-2 py-1 text-[11px] text-recall-textMuted">
            {TYPE_LABEL[fig.type]} · {fig.page_number}페이지
          </p>
        </div>
      ))}
    </div>
  );
}
