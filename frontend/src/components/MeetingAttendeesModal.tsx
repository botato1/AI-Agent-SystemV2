import { useEffect, useState } from "react";
import { getWorkspaceMembersApi, WorkspaceMemberInfo } from "../services/workspace";
import { getMeetingAttendeesApi, setMeetingAttendeesApi } from "../services/meeting";
import { CloseIcon, CheckIcon } from "./icons";

interface MeetingAttendeesModalProps {
  workspaceId: string;
  meetingId: string;
  meetingTitle: string;
  onClose: () => void;
  onSaved?: () => void;
  t: any;
}

export default function MeetingAttendeesModal({
  workspaceId,
  meetingId,
  meetingTitle,
  onClose,
  onSaved,
  t,
}: MeetingAttendeesModalProps) {
  const [members, setMembers] = useState<WorkspaceMemberInfo[] | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  // 모달을 연 시점의 참석자 스냅샷 - 여기 있던 사람은 "시작 시 참석자", 이후 새로 체크한 사람은 "새로 추가한 참석자"
  const [originalIds, setOriginalIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      const [membersRes, attendeesRes] = await Promise.all([
        getWorkspaceMembersApi(workspaceId),
        getMeetingAttendeesApi(workspaceId, meetingId),
      ]);
      if (cancelled) return;

      if (membersRes.status === "success") setMembers(membersRes.members);
      if (attendeesRes.status === "success") {
        const ids = new Set(attendeesRes.attendees.map((a) => a.user_id));
        setSelectedIds(ids);
        setOriginalIds(ids);
      }
      setIsLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, meetingId]);

  function toggle(userId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  }

  async function handleSave() {
    setIsSaving(true);
    setError(null);
    const res = await setMeetingAttendeesApi(workspaceId, meetingId, Array.from(selectedIds));
    setIsSaving(false);
    if (res.status === "success") {
      onSaved?.();
      onClose();
    } else {
      setError(res.message);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bg p-6 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between border-b border-recall-border pb-3">
          <div className="min-w-0">
            <p className="text-base font-semibold text-recall-text">{t.meeting_attendees_manage_title}</p>
            <p className="truncate text-sm text-recall-textMuted">{meetingTitle}</p>
          </div>
          <button onClick={onClose} className="flex-shrink-0 text-recall-textMuted hover:text-recall-text">
            <CloseIcon size={16} />
          </button>
        </div>

        {isLoading ? (
          <p className="text-base text-recall-textMuted">{t.common_loading}</p>
        ) : (
          (() => {
            const allMembers = members ?? [];
            // "시작 시 참석자"는 원래 있던 사람 중 지금도 체크돼있는 사람만 - 체크 해제한 사람을
            // 계속 여기 남겨두면(체크박스는 항상 true로 그려서) 체크를 풀어도 안 빠진 것처럼
            // 보이고, 동시에 selectedIds 기준인 "추가 가능" 목록에도 중복으로 나타났었다.
            const initialMembers = allMembers.filter((m) => originalIds.has(m.user_id) && selectedIds.has(m.user_id));
            const addedMembers = allMembers.filter((m) => selectedIds.has(m.user_id) && !originalIds.has(m.user_id));
            const pickableMembers = allMembers.filter((m) => !selectedIds.has(m.user_id));

            function renderRow(m: WorkspaceMemberInfo, isSelected: boolean) {
              return (
                <button
                  key={m.user_id}
                  type="button"
                  onClick={() => toggle(m.user_id)}
                  className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm hover:bg-white/5"
                >
                  <span className="text-recall-text">{m.display_name || m.username}</span>
                  <span
                    className={`flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border ${
                      isSelected
                        ? "border-recall-accent bg-recall-accent text-white"
                        : "border-recall-border text-transparent"
                    }`}
                  >
                    <CheckIcon size={12} />
                  </span>
                </button>
              );
            }

            return (
              <div className="max-h-80 space-y-3 overflow-y-auto">
                <div>
                  <p className="mb-1 px-0.5 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                    {t.meeting_minutes_attendees_initial}
                  </p>
                  {initialMembers.length === 0 ? (
                    <p className="px-0.5 text-xs text-recall-textMuted">{t.meeting_minutes_attendees_none}</p>
                  ) : (
                    <div className="space-y-1">{initialMembers.map((m) => renderRow(m, true))}</div>
                  )}
                </div>

                {addedMembers.length > 0 && (
                  <div>
                    <p className="mb-1 px-0.5 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                      {t.meeting_attendees_added_new}
                    </p>
                    <div className="space-y-1">{addedMembers.map((m) => renderRow(m, true))}</div>
                  </div>
                )}

                <div>
                  <p className="mb-1 px-0.5 text-xs font-semibold uppercase tracking-wide text-recall-textMuted/70">
                    {t.meeting_attendees_add_section}
                  </p>
                  {pickableMembers.length === 0 ? (
                    <p className="px-0.5 text-xs text-recall-textMuted">{t.meeting_attendees_no_addable}</p>
                  ) : (
                    <div className="space-y-1">{pickableMembers.map((m) => renderRow(m, false))}</div>
                  )}
                </div>
              </div>
            );
          })()
        )}

        {error && <p className="mt-3 text-sm text-recall-danger">{error}</p>}

        <div className="mt-5 flex justify-end gap-2 border-t border-recall-border pt-4">
          <button
            type="button"
            onClick={onClose}
            disabled={isSaving}
            className="rounded-lg border border-recall-border px-3.5 py-2 text-sm text-recall-textMuted hover:bg-white/5 disabled:opacity-50"
          >
            {t.task_cancel}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving || isLoading}
            className="rounded-lg bg-recall-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {isSaving ? t.meeting_export_saving : t.task_save}
          </button>
        </div>
      </div>
    </div>
  );
}
