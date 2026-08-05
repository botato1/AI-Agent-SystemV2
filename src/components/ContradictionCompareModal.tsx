// src/components/ContradictionCompareModal.tsx
import { Contradiction, ContradictionResolutionType } from "../services/contradiction";
import ContradictionMessage from "./ContradictionMessage";
import { CloseIcon } from "./icons";

interface ContradictionCompareModalProps {
  contradiction: Contradiction;
  onClose: () => void;
  onDismiss: (id: string) => void;
  onResolve: (id: string, resolutionType: ContradictionResolutionType) => void;
  onViewInMeeting?: () => void;
  onViewReference?: () => void;
  t: any;
}

export default function ContradictionCompareModal({
  contradiction,
  onClose,
  onDismiss,
  onResolve,
  onViewInMeeting,
  onViewReference,
  t,
}: ContradictionCompareModalProps) {
  // 채팅에서 감지된 모순은 백엔드가 반영/유지/무시 처리를 거부하므로(회의에서만 처리 가능),
  // 처리 버튼 없이 안내 문구만 보여준다. 본문에 기존 내용/새 발언이 이미 다 나와있어서
  // 별도로 이동시킬 곳은 없음 - 실제 처리 전까지는 홈 화면에 계속 남아 리마인드해준다.
  const isChatSourced = contradiction.source_type !== "meeting_segment";

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

        <ContradictionMessage contradiction={contradiction} expanded t={t} onViewReference={onViewReference ? () => onViewReference() : undefined} />

        <div className="mt-4 flex flex-col gap-2 border-t border-recall-border pt-4">
          {isChatSourced ? (
            <p className="text-center text-xs text-recall-textMuted">{t.contradiction_chat_source_notice}</p>
          ) : (
            <>
              <div className="flex gap-2">
                <button
                  onClick={() => onDismiss(contradiction.id)}
                  className="flex-1 rounded-lg border border-recall-border px-3 py-2 text-xs text-recall-textMuted hover:bg-white/5"
                >
                  {t.contradiction_dismiss}
                </button>
                <button
                  onClick={() => onResolve(contradiction.id, "keep_reference")}
                  className="flex-1 rounded-lg border border-recall-border px-3 py-2 text-xs text-recall-text hover:bg-white/5"
                >
                  {t.contradiction_keep}
                </button>
                <button
                  onClick={() => onResolve(contradiction.id, "change_acknowledged")}
                  className="flex-1 rounded-lg bg-recall-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90"
                >
                  {t.contradiction_apply}
                </button>
              </div>

              {onViewInMeeting && (
                <button
                  onClick={onViewInMeeting}
                  className="text-center text-xs text-recall-accent underline hover:opacity-80"
                >
                  {t.contradiction_view_in_meeting}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
