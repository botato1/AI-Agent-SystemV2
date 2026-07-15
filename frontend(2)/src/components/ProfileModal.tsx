// src/components/ProfileModal.tsx
import { useRef, useState } from "react";
import { User } from "../types";
import { AVATAR_COLORS } from "../data/avatarColors";
import Avatar from "./Avatar";
import { PencilIcon } from "./icons";

interface ProfileModalProps {
  user: User;
  onClose: () => void;
  onChangeAvatarColor: (color: string) => void;
  onChangeAvatarImage: (imageUrl: string) => void;
  t: any;
}

export default function ProfileModal({
  user,
  onClose,
  onChangeAvatarColor,
  onChangeAvatarImage,
  t,
}: ProfileModalProps) {
  const [showAvatarMenu, setShowAvatarMenu] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handlePickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    onChangeAvatarImage(URL.createObjectURL(file));
    setShowAvatarMenu(false);
  }

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/50">
      <div className="w-[360px] rounded-xl border border-recall-border bg-recall-bg p-5 text-recall-text">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-base font-medium">{t.profile_title}</p>
          <button
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-recall-textMuted hover:bg-white/5"
          >
            {t.btn_close}
          </button>
        </div>

        <div className="mb-5 flex flex-col items-center">
          <div className="relative">
            <Avatar user={user} size={72} />
            <button
              onClick={() => setShowAvatarMenu((v) => !v)}
              aria-label="Change profile"
              className="absolute -bottom-1 -left-1 flex h-6 w-6 items-center justify-center rounded-full border border-recall-border bg-recall-bgSoft text-recall-textMuted shadow-sm hover:text-recall-text"
            >
              <PencilIcon size={12} />
            </button>

            {showAvatarMenu && (
              <div className="absolute left-1/2 top-full z-30 mt-2 w-56 -translate-x-1/2 rounded-xl border border-recall-border bg-recall-bgSoft p-3 shadow-lg">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handlePickPhoto}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="mb-2 w-full rounded-lg border border-recall-border py-1.5 text-xs text-recall-text hover:bg-white/5"
                >
                  {t.profile_upload_photo}
                </button>
                <p className="mb-1.5 text-[11px] text-recall-textMuted">{t.profile_or_color}</p>
                <div className="flex flex-wrap gap-1.5">
                  {AVATAR_COLORS.map((color) => (
                    <button
                      key={color}
                      onClick={() => {
                        onChangeAvatarColor(color);
                        setShowAvatarMenu(false);
                      }}
                      style={{ backgroundColor: color }}
                      className={`h-6 w-6 rounded-full ${
                        !user.avatarImageUrl && user.avatarColor === color
                          ? "ring-2 ring-recall-accent ring-offset-2 ring-offset-recall-bgSoft"
                          : ""
                      }`}
                      aria-label={`Color ${color}`}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border border-recall-border">
          <div className="flex items-center justify-between border-b border-recall-border px-3 py-2.5 text-sm">
            <span className="text-recall-text">{t.profile_name}</span>
            <span className="text-recall-textMuted">{user.name}</span>
          </div>
          <div className="flex items-center justify-between border-b border-recall-border px-3 py-2.5 text-sm">
            <span className="text-recall-text">{t.profile_id}</span>
            <span className="text-recall-textMuted">{user.username}</span>
          </div>
          <div className="flex items-center justify-between px-3 py-2.5 text-sm">
            <span className="text-recall-text">{t.profile_change_pwd}</span>
            <span className="text-recall-accent">{t.profile_change}</span>
          </div>
        </div>
      </div>
    </div>
  );
}