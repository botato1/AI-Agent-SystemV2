import Avatar from "./Avatar";
import { hashAvatarColor } from "../data/avatarColors";

interface LiveMeetingBannerProps {
  title: string;
  isPaused: boolean;
  // 지금은 회의를 시작한 사람(Meeting.started_by)만 알 수 있어서 그 사람만 진하게 보여준다.
  // 실제로 지금 듣고 있는 나머지 참가자는 백엔드에 실시간 입장/퇴장 이벤트가 생기면 여기 배열에
  // { id, name, avatarUrl, isHost: false }로 추가해서 옅은 톤으로 같이 그리면 된다.
  hostUserId: string;
  hostName: string;
  hostAvatarUrl: string | null;
  onClick: () => void;
  t: any;
}

// 다른 사람이 지금 회의 중이라는 걸 홈/채팅/대시보드 등 어느 화면에 있든 알 수 있게 하는 얇은
// 배너 - 회의가 없으면 아예 렌더링 안 되고, 있을 때만 콘텐츠 영역 맨 위에 나타난다.
export default function LiveMeetingBanner({
  title,
  isPaused,
  hostUserId,
  hostName,
  hostAvatarUrl,
  onClick,
  t,
}: LiveMeetingBannerProps) {
  return (
    <button
      onClick={onClick}
      className="flex w-full flex-shrink-0 items-center gap-2 border-b border-recall-border bg-recall-bgSoft px-4 py-1.5 text-left hover:bg-white/5 transition"
    >
      <span
        className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${isPaused ? "bg-recall-textMuted" : "bg-recall-danger animate-pulse"}`}
      />
      <div className="flex -space-x-1.5">
        <div title={hostName} className="relative">
          <Avatar
            user={{ name: hostName, avatarColor: hashAvatarColor(hostUserId), avatarImageUrl: hostAvatarUrl }}
            size={20}
            className="border-2 border-recall-bgSoft"
          />
        </div>
      </div>
      <span className="truncate text-xs font-medium text-recall-text">{title}</span>
      <span className="flex-shrink-0 text-xs text-recall-textMuted">
        {isPaused ? t.sidebar_paused : t.sidebar_recording}
      </span>
    </button>
  );
}
