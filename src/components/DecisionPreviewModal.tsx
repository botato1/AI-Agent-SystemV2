import { useEffect, useState } from "react";
import { getWorkspaceDecisionsApi, WorkspaceDecision } from "../services/decision";
import {
  getMeetingApi,
  getMeetingDecisionsApi,
  getMeetingSegmentsApi,
  getMeetingSummaryApi,
  Meeting,
  MeetingSegment,
} from "../services/meeting";
import { CloseIcon } from "./icons";

interface DecisionPreviewModalProps {
  workspaceId: string;
  decisionId: string;
  onClose: () => void;
  // segmentId를 같이 주면, 회의 화면이 그냥 그 회의를 여는 데서 그치지 않고 스크립트 탭에서
  // 그 발언 위치까지 스크롤/하이라이트해준다 (근거가 된 바로 그 순간으로 이동).
  onOpenMeeting: (meetingId: string, segmentId?: string) => void;
  t: any;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

// 모순/결정변경 카드의 "근거 보기"에서 결정 참조(reference_type === "decision")를 눌렀거나,
// 대시보드 결정사항 카드를 눌렀을 때 쓴다.
//
// [변경 - 리뷰 반영] 처음엔 결정 제목/내용/사유를 그대로 다시 보여줬는데, 그건 이미 카드에
// 다 보이는 내용이라 눌러봐야 똑같은 걸 또 보는 셈이었다("근거 자료를 보고 싶은 거지, 방금
// 본 문장을 또 보고 싶은 게 아니다"). 그래서 이 결정의 근거가 된 실제 발언(source_segment_id로
// 찾은 회의 스크립트 원문)과 그 회의 정보를 보여주도록 바꿨다 - 진짜 "근거 자료".
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
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [meetingSummary, setMeetingSummary] = useState<string | null>(null);
  const [sourceSegment, setSourceSegment] = useState<MeetingSegment | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setNotFound(false);
      setMeeting(null);
      setMeetingSummary(null);
      setSourceSegment(null);

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

      if (found) {
        // 원본 회의로 아예 넘어가지 않아도 맥락을 알 수 있게, 그 회의의 한 줄 요약도 같이 보여준다.
        const [meetingRes, decisionsRes, summaryRes] = await Promise.all([
          getMeetingApi(workspaceId, found.meeting_id),
          getMeetingDecisionsApi(workspaceId, found.meeting_id),
          getMeetingSummaryApi(workspaceId, found.meeting_id),
        ]);
        if (cancelled) return;

        if (meetingRes.status === "success" && meetingRes.meeting) setMeeting(meetingRes.meeting);
        if (summaryRes.status === "success") setMeetingSummary(summaryRes.summary?.short_summary || null);

        const sourceSegmentId =
          decisionsRes.status === "success"
            ? decisionsRes.decisions.find((d) => d.id === decisionId)?.source_segment_id
            : null;

        if (sourceSegmentId) {
          const segmentsRes = await getMeetingSegmentsApi(workspaceId, found.meeting_id);
          if (cancelled) return;
          if (segmentsRes.status === "success") {
            setSourceSegment(segmentsRes.segments.find((s) => s.id === sourceSegmentId) || null);
          }
        }
      }

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
          // [수정 - 리뷰 반영] 결정 내용/사유는 카드에서 이미 보고 눌러 들어온 정보라 여기서
          // 또 반복하지 않는다. 여기선 "그래서 그 근거는 뭔데"에 대한 답만 - 실제 회의 발언과
          // 그 회의 요약, 그리고 그 발언이 나온 지점으로 바로 가는 버튼.
          <div className="space-y-3 text-sm">
            {meeting && (
              <p className="text-xs text-recall-textMuted">
                {meeting.title} · {formatDate(meeting.started_at || meeting.created_at)} ·{" "}
                {decision.status === "superseded" ? t.decision_status_superseded : t.decision_status_active}
              </p>
            )}

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                {t.decision_evidence_label}
              </p>
              {sourceSegment ? (
                <p className="rounded-lg bg-white/5 p-2.5 text-recall-text">
                  {sourceSegment.speaker_label && (
                    <span className="mr-1 font-medium text-recall-textMuted">{sourceSegment.speaker_label}:</span>
                  )}
                  "{sourceSegment.content}"
                </p>
              ) : (
                <p className="text-recall-textMuted">{t.decision_evidence_empty}</p>
              )}
            </div>

            {meetingSummary && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                  {t.decision_meeting_summary_label}
                </p>
                <p className="text-recall-textMuted">{meetingSummary}</p>
              </div>
            )}

            {/* 근거 발언이 없으면 "그 발언으로 이동"이 성립을 안 해서(갈 곳이 없음), 그냥
                회의 페이지만 여는 버튼을 굳이 남겨두지 않는다 - 요청대로 뺌. */}
            {sourceSegment && (
              <button
                type="button"
                onClick={() => onOpenMeeting(decision.meeting_id, sourceSegment.id ?? undefined)}
                className="w-full rounded-lg border border-recall-border py-2 text-xs font-medium text-recall-accent hover:bg-white/5"
              >
                {t.decision_preview_open_meeting}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
