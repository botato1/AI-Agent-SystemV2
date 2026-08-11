import { useEffect, useState } from "react";
import { getWorkspaceDecisionsApi, WorkspaceDecision } from "../services/decision";
import { CloseIcon } from "./icons";

interface DecisionPreviewModalProps {
  workspaceId: string;
  decisionId: string;
  onClose: () => void;
  onOpenMeeting: (meetingId: string) => void;
  t: any;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

// 모순/결정변경 카드의 "근거 보기"에서 결정 참조(reference_type === "decision")를 눌렀을 때 쓴다.
// 문서 참조는 미리보기 모달이 뜨는데 결정 참조만 페이지 전체가 대시보드로 넘어가버려서
// 회의 화면 맥락이 날아가는 문제가 있었다 - 문서처럼 그 자리에서 뜨는 모달로 통일한다.
//
// 참조된 결정이 이미 대체(superseded)됐을 수도 있어서(모순을 나중에 다시 보는 경우), active와
// superseded 둘 다 조회해서 합친다 - 워크스페이스 결정 목록 API를 새로 만들 필요 없이 재사용.
export default function DecisionPreviewModal({
  workspaceId,
  decisionId,
  onClose,
  onOpenMeeting,
  t,
}: DecisionPreviewModalProps) {
  const [decision, setDecision] = useState<WorkspaceDecision | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setNotFound(false);
      const [activeRes, supersededRes] = await Promise.all([
        getWorkspaceDecisionsApi(workspaceId, "active"),
        getWorkspaceDecisionsApi(workspaceId, "superseded"),
      ]);
      if (cancelled) return;

      const all = [
        ...(activeRes.status === "success" ? activeRes.decisions : []),
        ...(supersededRes.status === "success" ? supersededRes.decisions : []),
      ];
      const found = all.find((d) => d.id === decisionId) || null;
      setDecision(found);
      setNotFound(!found);
      setIsLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, decisionId]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl border border-recall-border bg-recall-bg p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between border-b border-recall-border pb-3">
          <p className="text-base font-semibold">{t.decision_preview_title}</p>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        {isLoading ? (
          <p className="text-sm text-recall-textMuted">{t.common_loading}</p>
        ) : notFound || !decision ? (
          <p className="text-sm text-recall-danger">{t.decision_preview_not_found}</p>
        ) : (
          <div className="space-y-3 text-sm">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                {decision.title}
              </p>
              <p className="text-recall-text">{decision.decision_text}</p>
            </div>
            {decision.reason && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                  {t.decision_reason_label}
                </p>
                <p className="text-recall-textMuted">{decision.reason}</p>
              </div>
            )}
            <p className="text-xs text-recall-textMuted">
              {decision.status === "superseded" ? t.decision_status_superseded : t.decision_status_active} ·{" "}
              {formatDate(decision.decided_at)}
            </p>
            <button
              type="button"
              onClick={() => onOpenMeeting(decision.meeting_id)}
              className="w-full rounded-lg border border-recall-border py-2 text-xs font-medium text-recall-accent hover:bg-white/5"
            >
              {t.decision_preview_open_meeting}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
