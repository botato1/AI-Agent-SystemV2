// src/components/ContradictionApplyForm.tsx
import { useState } from "react";
import { Contradiction } from "../services/contradiction";

interface ContradictionApplyFormProps {
  contradiction: Pick<Contradiction, "statement_text_snapshot" | "reason">;
  onApply: (values: { newDecisionText: string; newDecisionReason: string }) => Promise<boolean>;
  onCancel: () => void;
  t: any;
}

// 감지된 결정 변경 내용이 STT/LLM 오인식 등으로 틀렸을 때, 반영(change_acknowledged) 전에
// 결정 내용/사유를 직접 고쳐서 그 값으로 반영할 수 있게 하는 폼.
export default function ContradictionApplyForm({ contradiction, onApply, onCancel, t }: ContradictionApplyFormProps) {
  const [textDraft, setTextDraft] = useState(contradiction.statement_text_snapshot);
  const [reasonDraft, setReasonDraft] = useState(contradiction.reason ?? "");
  const [isApplying, setIsApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleApply() {
    const trimmedText = textDraft.trim();
    if (!trimmedText) {
      setError(t.contradiction_edit_error_empty);
      return;
    }

    setIsApplying(true);
    setError(null);
    const ok = await onApply({ newDecisionText: trimmedText, newDecisionReason: reasonDraft.trim() });
    setIsApplying(false);

    if (!ok) {
      setError(t.contradiction_edit_failed);
    }
  }

  return (
    <div className="mb-2 rounded-lg border border-recall-border bg-recall-bgMain p-2" onClick={(e) => e.stopPropagation()}>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-danger/80">
        {t.contradiction_apply_text_label}
      </p>
      <textarea
        autoFocus
        value={textDraft}
        onChange={(e) => setTextDraft(e.target.value)}
        rows={2}
        className="mb-2 w-full rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
      />
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
        {t.contradiction_apply_reason_label}
      </p>
      <textarea
        value={reasonDraft}
        onChange={(e) => setReasonDraft(e.target.value)}
        rows={2}
        className="mb-2 w-full rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
      />
      {error && <p className="mb-2 text-[11px] text-recall-danger">{error}</p>}
      <div className="flex gap-1.5">
        <button
          onClick={onCancel}
          disabled={isApplying}
          className="flex-1 rounded border border-recall-border px-2 py-1 text-[11px] text-recall-textMuted hover:bg-white/5 disabled:opacity-50"
        >
          {t.contradiction_edit_cancel}
        </button>
        <button
          onClick={handleApply}
          disabled={isApplying || !textDraft.trim()}
          className="flex-1 rounded bg-recall-accent px-2 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {isApplying ? t.contradiction_edit_saving : t.contradiction_apply}
        </button>
      </div>
    </div>
  );
}
