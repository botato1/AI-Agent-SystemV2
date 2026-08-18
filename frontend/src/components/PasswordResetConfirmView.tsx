import React, { useState } from "react";
import { confirmPasswordResetApi } from "../services/auth";
import { validatePassword } from "../data/passwordPolicy";

interface PasswordResetConfirmViewProps {
  resetToken: string; // URL 쿼리 파라미터 등에서 추출한 토큰
  onSuccess: () => void; // 성공 시 로그인 화면으로 이동
  t: any;
}

export default function PasswordResetConfirmView({
  resetToken,
  onSuccess,
  t,
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
      setError(t.profile_new_password_required);
      return;
    }

    const policyError = validatePassword(newPassword);
    if (policyError) {
      setError(policyError);
      return;
    }

    if (newPassword !== confirmPassword) {
      setError(t.reset_confirm_mismatch);
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
        <h1 className="mb-1 text-xl font-semibold">{t.reset_confirm_title}</h1>
        <p className="mb-5 text-sm text-recall-textMuted">
          {t.reset_confirm_desc}
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">{t.profile_password_new}</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={t.profile_password_new_placeholder}
              className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-base focus:border-recall-accent focus:outline-none"
            />
            <p className="mt-1 text-xs text-recall-textMuted">
              {t.profile_password_policy_hint}
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm text-recall-textMuted">{t.profile_password_confirm}</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={t.profile_password_confirm_placeholder}
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
            {isSubmitting ? t.reset_confirm_submitting : t.reset_confirm_submit}
          </button>
        </form>
      </div>
    </div>
  );
}