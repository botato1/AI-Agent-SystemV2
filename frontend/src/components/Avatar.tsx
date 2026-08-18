import { User } from "../types";
import { PersonIcon } from "./icons";

interface AvatarProps {
  user: Pick<User, "name" | "avatarColor" | "avatarImageUrl">;
  size: number;
  className?: string;
}

// 프로필 동그라미 - 사진을 업로드했으면 사진, 아니면 색상 배경 + 이름 첫 글자
// 이름을 아직 안 썼으면 색상도 빼고 무채색 배경 + 사람 아이콘으로 대체
export default function Avatar({ user, size, className = "" }: AvatarProps) {
  if (user.avatarImageUrl) {
    return (
      <img
        src={user.avatarImageUrl}
        alt={user.name}
        style={{ width: size, height: size }}
        className={`flex-shrink-0 rounded-full object-cover ${className}`}
      />
    );
  }

  const trimmed = user.name.trim();

  if (!trimmed) {
    return (
      <div
        style={{ width: size, height: size }}
        className={`flex flex-shrink-0 items-center justify-center rounded-full bg-recall-border text-recall-textMuted ${className}`}
      >
        <PersonIcon size={size * 0.55} />
      </div>
    );
  }

  return (
    <div
      style={{ width: size, height: size, backgroundColor: user.avatarColor }}
      className={`flex flex-shrink-0 items-center justify-center rounded-full font-medium text-white ${className}`}
    >
      <span style={{ fontSize: size * 0.42 }}>{trimmed.charAt(0).toUpperCase()}</span>
    </div>
  );
}