import { LiveMeetingStatus, LiveSegment, ContradictionAlert } from "../hooks/useLiveMeeting";
import { Meeting, RecordingMode } from "../services/meeting";
import MeetingsPanel from "./MeetingsPanel";

interface VoiceMeetingViewProps {
  workspaceId: string;
  status: LiveMeetingStatus;
  meeting: Meeting | null;
  segments: LiveSegment[];
  partial: { confirmed: string; tentative: string };
  contradictionAlerts: ContradictionAlert[];
  errorMessage: string | null;
  joinableMeeting: Meeting | null;
  onStart: (
    title: string,
    relatedRoomId?: string,
    attendeeIds?: string[],
    location?: string,
    recordingMode?: RecordingMode
  ) => void;
  onJoin: (meetingId: string) => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onReset: () => void;
  onMapLiveSpeakers: (mapping: Record<string, string>) => void;
  onRenameLive: (title: string) => void;
  t: any;
}

export default function VoiceMeetingView({
  workspaceId,
  status,
  meeting,
  segments,
  partial,
  contradictionAlerts,
  errorMessage,
  joinableMeeting,
  onStart,
  onJoin,
  onPause,
  onResume,
  onStop,
  onReset,
  onMapLiveSpeakers,
  onRenameLive,
  t,
}: VoiceMeetingViewProps) {
  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain text-recall-text">
      <div className="flex items-center border-b border-recall-border p-3">
        <p className="text-base font-medium">{t.sidebar_voice_meeting}</p>
      </div>

      <MeetingsPanel
        workspaceId={workspaceId}
        liveStatus={status}
        liveMeeting={meeting}
        liveSegments={segments}
        livePartial={partial}
        liveContradictionAlerts={contradictionAlerts}
        liveError={errorMessage}
        joinableMeeting={joinableMeeting}
        onStartLive={onStart}
        onJoinLive={onJoin}
        onPauseLive={onPause}
        onResumeLive={onResume}
        onStopLive={onStop}
        onResetLive={onReset}
        onMapLiveSpeakers={onMapLiveSpeakers}
        onRenameLive={onRenameLive}
        t={t}
      />
    </div>
  );
}
