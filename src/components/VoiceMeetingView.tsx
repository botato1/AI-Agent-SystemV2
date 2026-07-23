import { LiveMeetingStatus, LiveSegment } from "../hooks/useLiveMeeting";
import { Meeting } from "../services/meeting";
import MeetingsPanel from "./MeetingsPanel";

interface VoiceMeetingViewProps {
  workspaceId: string;
  status: LiveMeetingStatus;
  meeting: Meeting | null;
  segments: LiveSegment[];
  partial: { confirmed: string; tentative: string };
  errorMessage: string | null;
  onStart: (title: string) => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onReset: () => void;
  t: any;
}

export default function VoiceMeetingView({
  workspaceId,
  status,
  meeting,
  segments,
  partial,
  errorMessage,
  onStart,
  onPause,
  onResume,
  onStop,
  onReset,
  t,
}: VoiceMeetingViewProps) {
  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
      <div className="flex items-center border-b border-recall-border p-3">
        <p className="text-sm font-medium">{t.sidebar_voice_meeting}</p>
      </div>

      <MeetingsPanel
        workspaceId={workspaceId}
        liveStatus={status}
        liveMeeting={meeting}
        liveSegments={segments}
        livePartial={partial}
        liveError={errorMessage}
        onStartLive={onStart}
        onPauseLive={onPause}
        onResumeLive={onResume}
        onStopLive={onStop}
        onResetLive={onReset}
      />
    </div>
  );
}
