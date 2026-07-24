import { useEffect, useState } from "react";
import {
  getWorkspaceMembersApi,
  deleteWorkspaceMemberApi,
  updateMemberRoleApi,
  WorkspaceMemberInfo,
} from "../services/workspace";
import { TrashIcon } from "./icons";

interface ManageMembersModalProps {
  workspaceId: string;
  workspaceName: string;
  currentUserId: string;
  onClose: () => void;
  onOpenInviteModal?: () => void;
}

export default function ManageMembersModal({
  workspaceId,
  workspaceName,
  currentUserId,
  onClose,
  onOpenInviteModal,
}: ManageMembersModalProps) {
  const [members, setMembers] = useState<WorkspaceMemberInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [processingUserId, setProcessingUserId] = useState<string | null>(null);

  const myRole = members.find((m) => (m.user_id || m.id) === currentUserId)?.role;
  const isOwner = myRole === "owner";

  // 삭제 확인 모달을 위한 상태
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    async function loadMembers() {
      setIsLoading(true);
      setErrorMessage(null);

      const res = await getWorkspaceMembersApi(workspaceId);

      setIsLoading(false);
      if (res.status === "success") {
        setMembers(res.members);
      } else {
        setErrorMessage(res.message);
      }
    }

    loadMembers();
  }, [workspaceId]);

  // 멤버 제거 실제 처리
  const executeDeleteMember = async () => {
    if (!deleteTarget) return;

    const { id: userId } = deleteTarget;
    setProcessingUserId(userId);
    setErrorMessage(null);

    const res = await deleteWorkspaceMemberApi(workspaceId, userId);

    setProcessingUserId(null);
    setDeleteTarget(null); // 삭제 확인 모달 닫기

    if (res.status === "success") {
      setMembers((prev) => prev.filter((m) => (m.user_id || m.id) !== userId));
    } else {
      setErrorMessage(res.message);
    }
  };

  // 멤버 역할 변경 처리
  const handleRoleChange = async (userId: string, newRole: "owner" | "member") => {
    setProcessingUserId(userId);
    setErrorMessage(null);

    const res = await updateMemberRoleApi(workspaceId, userId, newRole);

    setProcessingUserId(null);

    if (res.status === "success") {
      setMembers((prev) =>
        prev.map((m) =>
          (m.user_id || m.id) === userId ? { ...m, role: newRole } : m
        )
      );
    } else {
      setErrorMessage(res.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-2xl text-recall-text">
        {/* 헤더 */}
        <div className="flex items-center justify-between border-b border-recall-border pb-3 mb-4">
          <div>
            <h3 className="text-lg font-bold">
              팀원 관리 <span className="text-sm font-normal text-recall-textMuted">({workspaceName})</span>
            </h3>
            <p className="text-sm text-recall-textMuted mt-0.5">
              총 {members.length}명의 팀원이 참여 중입니다.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-recall-textMuted hover:text-recall-text transition text-xl"
          >
            ✕
          </button>
        </div>

        {/* 에러 메시지 알림 */}
        {errorMessage && (
          <div className="mb-3 rounded-lg bg-recall-danger/10 border border-recall-danger/30 p-2.5 text-sm text-recall-danger flex items-center justify-between">
            <span>⚠️ {errorMessage}</span>
            <button onClick={() => setErrorMessage(null)} className="text-recall-danger text-sm font-bold ml-2">
              ✕
            </button>
          </div>
        )}

        {/* 본문 (멤버 목록) */}
        {isLoading ? (
          <div className="py-12 text-center text-sm text-recall-textMuted">
            멤버 목록을 불러오는 중입니다...
          </div>
        ) : (
          <div className="max-h-80 space-y-2.5 overflow-y-auto pr-1">
            {members.map((m) => {
              const targetUserId: string = m.user_id || m.id || "";
              const isProcessing = processingUserId === targetUserId;
              const displayName = m.display_name || m.username;
              const isSelf = targetUserId === currentUserId;

              return (
                <div
                  key={targetUserId}
                  className="flex items-center justify-between rounded-xl border border-recall-border bg-recall-bgMain p-3.5"
                >
                  {/* 팀원 정보 영역 */}
                  <div className="flex items-center gap-3 min-w-0 pr-2">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-recall-accent/20 text-recall-accent font-bold text-base">
                      {displayName.slice(0, 1).toUpperCase()}
                    </div>

                    <div className="flex flex-col min-w-0">
                      <span className="truncate text-base font-bold text-recall-text leading-tight">
                        {displayName}
                        {isSelf && <span className="ml-1 text-[11px] font-normal text-recall-textMuted">(나)</span>}
                      </span>
                      <span className="truncate text-sm text-recall-textMuted mt-0.5">
                        @{m.username}
                      </span>
                    </div>
                  </div>

                  {/* 컨트롤 영역 */}
                  <div className="flex items-center gap-2 shrink-0">
                    {isOwner && !isSelf ? (
                      <select
                        value={m.role}
                        disabled={isProcessing}
                        onChange={(e) =>
                          handleRoleChange(targetUserId, e.target.value as "owner" | "member")
                        }
                        title="역할 변경"
                        className="rounded-lg border border-recall-border bg-recall-bgSoft px-2 py-1 text-sm text-recall-text outline-none focus:border-recall-accent disabled:opacity-50"
                      >
                        <option value="member">일반 멤버</option>
                        <option value="owner">소유자</option>
                      </select>
                    ) : (
                      <span className="rounded-lg bg-recall-accent/10 px-2 py-1 text-xs font-semibold text-recall-accent">
                        {m.role === "owner" ? "소유자" : "일반 멤버"}
                      </span>
                    )}

                    {isOwner && !isSelf && (
                      <button
                        disabled={isProcessing}
                        onClick={() => setDeleteTarget({ id: targetUserId, name: displayName })}
                        title="팀원 제거"
                        className="flex h-8 w-8 items-center justify-center rounded-lg text-recall-textMuted hover:bg-recall-danger/10 hover:text-recall-danger transition disabled:opacity-50"
                      >
                        <TrashIcon size={16} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* 하단 버튼 */}
        <div className="flex items-center justify-between border-t border-recall-border pt-4 mt-4">
          {onOpenInviteModal && (
            <button
              onClick={() => {
                onClose();
                onOpenInviteModal();
              }}
              className="rounded-lg bg-recall-accent/15 px-3.5 py-2 text-sm font-semibold text-recall-accent hover:bg-recall-accent hover:text-white transition"
            >
              + 팀원 초대하기
            </button>
          )}
          <button
            onClick={onClose}
            className="ml-auto rounded-lg border border-recall-border px-4 py-2 text-sm text-recall-textMuted hover:bg-white/5 transition"
          >
            닫기
          </button>
        </div>
      </div>

      {/* 💡 삭제 확인 커스텀 모달 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-5 text-recall-text shadow-2xl animate-in fade-in zoom-in duration-150">
            <div className="flex items-center gap-3 text-recall-danger mb-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-recall-danger/10 text-xl">
                🗑️
              </div>
              <h4 className="text-lg font-bold text-recall-text">팀원 제거</h4>
            </div>

            <p className="text-sm text-recall-textMuted leading-relaxed mb-5">
              <span className="font-bold text-recall-text">'{deleteTarget.name}'</span> 님을 워크스페이스에서 제거하시겠습니까? 이 작업은 즉시 반영됩니다.
            </p>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="rounded-lg border border-recall-border px-3.5 py-2 text-sm text-recall-textMuted hover:bg-white/5 transition"
              >
                취소
              </button>
              <button
                type="button"
                onClick={executeDeleteMember}
                className="rounded-lg bg-recall-danger px-3.5 py-2 text-sm font-semibold text-white hover:opacity-90 transition shadow-md shadow-recall-danger/20"
              >
                제거하기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}