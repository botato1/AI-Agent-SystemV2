// src/components/ContradictionEditForm.tsx
import { useState } from "react";
import { Contradiction } from "../services/contradiction";

interface ContradictionEditFormProps {
  contradiction: Pick<Contradiction, "statement_text_snapshot" | "reference_text_snapshot">;
  onSave: (updates: { statement_text_snapshot: string; reference_text_snapshot: string }) => Promise<boolean>;
  onCancel: () => void;
  t: any;
}

// 잘못 감지된 모순(=회의 도움)의 "기존 내용"/"새 발언" 스냅샷 텍스트를 직접 고칠 수 있는 폼.
// 감지 결과를 무시하는 대신, 오탈자나 STT 오인식 등으로 잘못 뜬 내용 자체를 바로잡을 때 쓴다.
export default function ContradictionEditForm({ contradiction, onSave, onCancel, t }: ContradictionEditFormProps) {
  const [existingDraft, setExistingDraft] = useState(contradiction.reference_text_snapshot);
  const [newDraft, setNewDraft] = useState(contradiction.statement_text_snapshot);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    const trimmedExisting = existingDraft.trim();
    const trimmedNew = newDraft.trim();
    if (!trimmedExisting || !trimmedNew) {
      setError(t.contradiction_edit_error_empty);
      return;
    }

    setIsSaving(true);
    setError(null);
    const ok = await onSave({
      statement_text_snapshot: trimmedNew,
      reference_text_snapshot: trimmedExisting,
    });
    setIsSaving(false);

    if (!ok) {
      setError(t.contradiction_edit_failed);
    }
  }

  return (
    <div className="mb-2 rounded-lg border border-recall-border bg-recall-bgMain p-2" onClick={(e) => e.stopPropagation()}>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
        {t.contradiction_edit_existing_label}
      </p>
      <textarea
        autoFocus
        value={existingDraft}
        onChange={(e) => setExistingDraft(e.target.value)}
        rows={2}
        className="mb-2 w-full rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
      />
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-danger/80">
        {t.contradiction_edit_new_label}
      </p>
      <textarea
        value={newDraft}
        onChange={(e) => setNewDraft(e.target.value)}
        rows={2}
        className="mb-2 w-full rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-1.5 text-xs text-recall-text outline-none focus:border-recall-accent"
      />
      {error && <p className="mb-2 text-[11px] text-recall-danger">{error}</p>}
      <div className="flex gap-1.5">
        <button
          onClick={onCancel}
          disabled={isSaving}
          className="flex-1 rounded border border-recall-border px-2 py-1 text-[11px] text-recall-textMuted hover:bg-white/5 disabled:opacity-50"
        >
          {t.contradiction_edit_cancel}
        </button>
        <button
          onClick={handleSave}
          disabled={isSaving || !existingDraft.trim() || !newDraft.trim()}
          className="flex-1 rounded bg-recall-accent px-2 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {isSaving ? t.contradiction_edit_saving : t.contradiction_edit_save}
        </button>
      </div>
    </div>
  );
}
