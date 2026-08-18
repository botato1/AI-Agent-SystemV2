// src/components/ContradictionCompareModal.tsx
import { useState } from "react";
import { Contradiction, ContradictionResolutionType } from "../services/contradiction";
import ContradictionMessage from "./ContradictionMessage";
import ContradictionEditForm from "./ContradictionEditForm";
import ContradictionApplyForm from "./ContradictionApplyForm";
import { CloseIcon } from "./icons";
import { showConfirm } from "../lib/confirm";

interface ContradictionCompareModalProps {
  contradiction: Contradiction;
  onClose: () => void;
  onResolve: (
    id: string,
    resolutionType: ContradictionResolutionType,
    newDecisionText?: string,
    newDecisionReason?: string
  ) => void;
  onUpdate?: (
    id: string,
    updates: { statement_text_snapshot: string; reference_text_snapshot: string }
  ) => Promise<boolean>;
  onViewInMeeting?: () => void;
  onViewReference?: () => void;
  onViewDecision?: () => void;
  t: any;
}

export default function ContradictionCompareModal({
  contradiction,
  onClose,
  onResolve,
  onUpdate,
  onViewInMeeting,
  onViewReference,
  onViewDecision,
  t,
}: ContradictionCompareModalProps) {
  // 채팅에서 감지된 결정(decision) 변경만 백엔드가 여전히 409로 막는다(회의에서 감지된 결정
  // 변경은 그대로 반영 가능). dismiss/keep_reference는 source_type이나 reference_type과
  // 무관하게 항상 가능하다.
  const canApplyChange = !(contradiction.source_type === "room_message" && contradiction.reference_type === "decision");
  const isDecisionCard = contradiction.reference_type === "decision";
  const [isEditing, setIsEditing] = useState(false);
  const [isApplying, setIsApplying] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-2xl border border-recall-border bg-recall-bg p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between border-b border-recall-border pb-3">
          <p className="text-base font-semibold text-recall-text">{t.contradiction_compare_title}</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        {isEditing ? (
          <ContradictionEditForm
            contradiction={contradiction}
            onCancel={() => setIsEditing(false)}
            onSave={async (updates) => {
              if (!onUpdate) return false;
              const ok = await onUpdate(contradiction.id, updates);
              if (ok) setIsEditing(false);
              return ok;
            }}
            t={t}
          />
        ) : isApplying ? (
          <ContradictionApplyForm
            contradiction={contradiction}
            onCancel={() => setIsApplying(false)}
            onApply={async ({ newDecisionText, newDecisionReason }) => {
              const confirmed = await showConfirm(t.contradiction_apply_confirm, t.contradiction_apply, t.task_cancel);
              if (!confirmed) return false;
              onResolve(contradiction.id, "change_acknowledged", newDecisionText, newDecisionReason);
              return true;
            }}
            t={t}
          />
        ) : (
          <ContradictionMessage
            contradiction={contradiction}
            expanded
            t={t}
            onViewReference={onViewReference ? () => onViewReference() : undefined}
            onViewDecision={onViewDecision ? () => onViewDecision() : undefined}
          />
        )}

        <div className="mt-4 flex flex-col gap-2 border-t border-recall-border pt-4">
          {!isEditing && !isApplying && (
            <div className="flex gap-2">
              {onUpdate && (
                <button
                  onClick={() => setIsEditing(true)}
                  className="flex-1 rounded-lg border border-recall-border px-3 py-2 text-xs text-recall-textMuted hover:bg-white/5"
                >
                  {t.contradiction_edit}
                </button>
              )}
              <button
                onClick={() => onResolve(contradiction.id, "keep_reference")}
                className="flex-1 rounded-lg border border-recall-border px-3 py-2 text-xs text-recall-text hover:bg-white/5"
              >
                {t.contradiction_keep}
              </button>
              {canApplyChange && (
                <button
                  onClick={async () => {
                    // 결정 변경(decision)은 반영 전에 내용을 직접 고칠 수 있는 폼을 먼저 보여준다.
                    if (isDecisionCard) {
                      setIsApplying(true);
                      return;
                    }
                    const ok = await showConfirm(t.contradiction_apply_confirm, t.contradiction_apply, t.task_cancel);
                    if (ok) onResolve(contradiction.id, "change_acknowledged");
                  }}
                  className="flex-1 rounded-lg bg-recall-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90"
                >
                  {t.contradiction_apply}
                </button>
              )}
            </div>
          )}

          {!canApplyChange && (
            <p className="text-center text-xs text-recall-textMuted">{t.contradiction_decision_apply_notice}</p>
          )}

          {onViewInMeeting && (
            <button
              onClick={onViewInMeeting}
              className="text-center text-xs text-recall-accent underline hover:opacity-80"
            >
              {t.contradiction_view_in_meeting}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
