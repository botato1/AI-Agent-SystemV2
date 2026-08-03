import React, { useState } from "react";
import { inviteWorkspaceMemberApi } from "../services/workspace";

interface InviteMemberModalProps {
  workspaceId: string;
  workspaceName: string;
  onClose: () => void;
}

export default function InviteMemberModal({
  workspaceId,
  workspaceName,
  onClose,
}: InviteMemberModalProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"member" | "owner">("member");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;

    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    const res = await inviteWorkspaceMemberApi(workspaceId, email, role);

    setIsLoading(false);

    if (res.status === "success") {
      setSuccessMessage(
        res.result === "invited"
          ? `${res.email || email} 로 초대 메일을 보냈습니다! (7일간 유효)`
          : `${res.member?.display_name || email} 님을 멤버로 추가했습니다!`
      );
      setEmail("");
      setTimeout(() => {
        onClose();
      }, 1600);
    } else {
      setErrorMessage(res.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-2xl text-recall-text">
        <div className="flex items-center justify-between border-b border-recall-border pb-3 mb-4">
          <h3 className="text-lg font-bold">
            팀원 초대 <span className="text-sm font-normal text-recall-textMuted">({workspaceName})</span>
          </h3>
          <button
            onClick={onClose}
            className="text-recall-textMuted hover:text-recall-text transition text-xl"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-recall-textMuted mb-1.5">
              이메일 주소 <span className="text-recall-accent">*</span>
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="초대할 팀원의 이메일을 입력하세요"
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-sm text-recall-text outline-none focus:border-recall-accent"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-recall-textMuted mb-1.5">
              권한 설정 (Role)
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as "member" | "owner")}
              className="w-full rounded-lg border border-recall-border bg-recall-bgMain px-3 py-2 text-sm text-recall-text outline-none focus:border-recall-accent"
            >
              <option value="member">일반 멤버 (Member)</option>
              <option value="owner">소유자 (Owner)</option>
            </select>
          </div>

          {errorMessage && (
            <div className="rounded-lg bg-recall-danger/10 border border-recall-danger/30 p-2.5 text-sm text-recall-danger">
              ⚠️ {errorMessage}
            </div>
          )}

          {successMessage && (
            <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-2.5 text-sm text-emerald-400">
              ✅ {successMessage}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-recall-border px-4 py-2 text-sm text-recall-textMuted hover:bg-white/5 transition"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isLoading || !email.trim()}
              className="rounded-lg bg-recall-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 transition"
            >
              {isLoading ? "초대 중..." : "초대하기"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}