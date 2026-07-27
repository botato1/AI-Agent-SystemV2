import React, { useState } from "react";
import { confirmPasswordResetApi } from "../services/auth";

interface PasswordResetConfirmViewProps {
  resetToken: string; // URL 쿼리 파라미터 등에서 추출한 토큰
  onSuccess: () => void; // 성공 시 로그인 화면으로 이동
}

export default function PasswordResetConfirmView({
  resetToken,
  onSuccess,
}: PasswordResetConfirmViewProps) {
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!newPassword) {
      setError("새 비밀번호를 입력해 주세요.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("비밀번호 확인이 일치하지 않습니다.");
      return;
    }

    setIsSubmitting(true);

    const res = await confirmPasswordResetApi(resetToken, newPassword);

    setIsSubmitting(false);

    if (res.status === "success") {
      setSuccessMsg(res.message);
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } else {
      setError(res.message);
    }
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-recall-bg p-4 text-recall-text">
      <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-lg">
        <h1 className="mb-1 text-xl font-semibold">새 비밀번호 설정</h1>
        <p className="mb-5 text-sm text-recall-textMuted">
          새로 사용할 비밀번호를 입력해 주세요.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">새 비밀번호</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="새 비밀번호 입력"
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base focus:border-recall-accent focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">새 비밀번호 확인</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="새 비밀번호 다시 입력"
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base focus:border-recall-accent focus:outline-none"
            />
          </div>

          {error && <p className="text-sm text-recall-danger">{error}</p>}
          {successMsg && <p className="text-sm text-emerald-400 font-medium">{successMsg}</p>}

          <button
            type="submit"
            disabled={isSubmitting}
            className="mt-3 w-full rounded-lg bg-recall-accent py-2 text-base font-medium text-white hover:opacity-90 disabled:opacity-50 transition"
          >
            {isSubmitting ? "변경 중..." : "비밀번호 변경하기"}
          </button>
        </form>
      </div>
    </div>
  );
}