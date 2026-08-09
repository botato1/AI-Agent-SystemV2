import { useState } from "react";
import { MeetingSegment, SplitSegmentParams } from "../services/meeting";
import { CloseIcon } from "./icons";

interface SplitSegmentModalProps {
  segment: MeetingSegment;
  onClose: () => void;
  onSplit: (segmentId: string, params: SplitSegmentParams) => Promise<boolean>;
  t: any;
}

// 원본 내용 중간 지점(가장 가까운 공백)에서 1차로 나눠서 편집 시작점으로 제공
function defaultSplitPoint(content: string): number {
  const mid = Math.floor(content.length / 2);
  const spaceBefore = content.lastIndexOf(" ", mid);
  const spaceAfter = content.indexOf(" ", mid);
  if (spaceBefore === -1 && spaceAfter === -1) return mid;
  if (spaceBefore === -1) return spaceAfter;
  if (spaceAfter === -1) return spaceBefore;
  return mid - spaceBefore <= spaceAfter - mid ? spaceBefore : spaceAfter;
}

export default function SplitSegmentModal({ segment, onClose, onSplit, t }: SplitSegmentModalProps) {
  const splitPoint = defaultSplitPoint(segment.content);
  const [firstContent, setFirstContent] = useState(segment.content.slice(0, splitPoint).trim());
  const [secondContent, setSecondContent] = useState(segment.content.slice(splitPoint).trim());
  const [firstSpeakerLabel, setFirstSpeakerLabel] = useState(segment.speaker_label ?? "");
  const [secondSpeakerLabel, setSecondSpeakerLabel] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = firstContent.trim().length > 0 && secondContent.trim().length > 0;

  async function handleSubmit() {
    if (!canSubmit) return;
    setIsSaving(true);
    setError(null);
    const ok = await onSplit(segment.id, {
      firstContent: firstContent.trim(),
      firstSpeakerLabel: firstSpeakerLabel.trim() || undefined,
      secondContent: secondContent.trim(),
      secondSpeakerLabel: secondSpeakerLabel.trim() || undefined,
    });
    setIsSaving(false);
    if (ok) onClose();
    else setError(t.meeting_split_failed);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-2xl text-recall-text">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold">{t.meeting_split_title}</h3>
          <button onClick={onClose} className="text-recall-textMuted hover:text-recall-text" aria-label={t.btn_close}>
            <CloseIcon size={16} />
          </button>
        </div>

        <p className="mb-3 rounded-lg bg-white/5 p-2.5 text-xs text-recall-textMuted">{segment.content}</p>

        <div className="space-y-4">
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-sm font-semibold text-recall-textMuted">{t.meeting_split_first_label}</label>
              <input
                value={firstSpeakerLabel}
                onChange={(e) => setFirstSpeakerLabel(e.target.value)}
                placeholder={t.meeting_split_speaker_placeholder}
                className="w-32 rounded border border-recall-border bg-recall-bgMain px-2 py-1 text-xs text-recall-text outline-none focus:border-recall-accent"
              />
            </div>
            <textarea
              autoFocus
              value={firstContent}
              onChange={(e) => setFirstContent(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-sm text-recall-text outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-sm font-semibold text-recall-textMuted">{t.meeting_split_second_label}</label>
              <input
                value={secondSpeakerLabel}
                onChange={(e) => setSecondSpeakerLabel(e.target.value)}
                placeholder={t.meeting_split_speaker_placeholder}
                className="w-32 rounded border border-recall-border bg-recall-bgMain px-2 py-1 text-xs text-recall-text outline-none focus:border-recall-accent"
              />
            </div>
            <textarea
              value={secondContent}
              onChange={(e) => setSecondContent(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-sm text-recall-text outline-none focus:border-recall-accent"
            />
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-recall-danger">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={isSaving}
            className="rounded-lg border border-recall-border px-3.5 py-2 text-sm text-recall-textMuted hover:bg-white/5 disabled:opacity-50"
          >
            {t.task_cancel}
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSaving || !canSubmit}
            className="rounded-lg bg-recall-accent px-3.5 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {isSaving ? t.meeting_export_saving : t.meeting_split_confirm_btn}
          </button>
        </div>
      </div>
    </div>
  );
}
