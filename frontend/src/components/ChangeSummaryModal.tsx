import { Contradiction, ChangeSummaryDraft } from "../services/contradiction";
import { CloseIcon, WarningIcon } from "./icons";

interface ChangeSummaryModalProps {
  contradiction: Contradiction;
  changeSummary: ChangeSummaryDraft | null;
  onClose: () => void;
  t: any;
}

// "반영"(change_acknowledged) 처리 직후 표시하는 모달. 요약 자체는 백엔드가 LLM으로
// 백그라운드 생성하므로(pending → completed/failed) 완료될 때까지 로딩 상태로 보여준다.
export default function ChangeSummaryModal({
  contradiction,
  changeSummary,
  onClose,
  t,
}: ChangeSummaryModalProps) {
  const originalText = changeSummary?.original_reference_text ?? contradiction.reference_text_snapshot;
  const acceptedText = changeSummary?.accepted_change_text ?? contradiction.statement_text_snapshot;
  const status = changeSummary?.generation_status ?? "pending";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-2xl border border-recall-border bg-recall-bg p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between border-b border-recall-border pb-3">
          <p className="text-base font-semibold text-recall-text">{t.change_summary_title}</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        <p className="mb-4 text-sm text-recall-textMuted">{t.change_summary_desc}</p>

        <div className="flex flex-col gap-3 max-h-[60vh] overflow-y-auto pr-1">
          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-recall-textMuted/70">
              {t.change_summary_original}
            </p>
            <p className="text-sm text-recall-textMuted">{originalText}</p>
          </div>

          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-recall-accent/80">
              {t.change_summary_accepted}
            </p>
            <p className="text-sm text-recall-text">{acceptedText}</p>
          </div>

          <div className="rounded-lg border border-recall-border bg-recall-bgSoft p-3">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-recall-textMuted/70">
              {t.change_summary_generated}
            </p>
            {status === "failed" ? (
              <p className="flex items-center gap-1.5 text-sm text-recall-danger">
                <WarningIcon size={13} className="flex-shrink-0" />
                {t.change_summary_failed}
              </p>
            ) : status === "completed" && changeSummary?.generated_summary ? (
              <p className="text-sm text-recall-text">{changeSummary.generated_summary}</p>
            ) : (
              <p className="flex items-center gap-2 text-sm text-recall-textMuted">
                <span className="h-3.5 w-3.5 flex-shrink-0 animate-spin rounded-full border-2 border-recall-border border-t-recall-accent" />
                {t.change_summary_generating}
              </p>
            )}
          </div>
        </div>

        <div className="mt-5 flex justify-end border-t border-recall-border pt-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-recall-accent px-4 py-1.5 text-sm font-medium text-white hover:opacity-90 transition"
          >
            {t.btn_close}
          </button>
        </div>
      </div>
    </div>
  );
}
