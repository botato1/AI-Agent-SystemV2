import { LiveMeetingStatus, LiveSegment, ContradictionAlert, AudioQualityAlert } from "../hooks/useLiveMeeting";
import { Meeting, RecordingMode, AgendaReminderPopup } from "../services/meeting";
import MeetingsPanel from "./MeetingsPanel";

interface VoiceMeetingViewProps {
  workspaceId: string;
  avatarUrlByName: Record<string, string | null>;
  status: LiveMeetingStatus;
  meeting: Meeting | null;
  segments: LiveSegment[];
  partial: { confirmed: string; tentative: string };
  contradictionAlerts: ContradictionAlert[];
  onClearContradictionAlert: (contradictionId: string) => void;
  audioQualityAlerts: AudioQualityAlert[];
  onClearAudioQualityAlert: (alertId: string) => void;
  agendaReminder: AgendaReminderPopup | null;
  onClearAgendaReminder: () => void;
  errorMessage: string | null;
  joinableMeeting: Meeting | null;
  isViewer: boolean;
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
  onLeave: () => void;
  onReset: () => void;
  onMapLiveSpeakers: (mapping: Record<string, string>) => void;
  onEditLiveSegment: (segmentId: string, content: string) => Promise<boolean>;
  onRenameLive: (title: string) => void;
  t: any;
}

export default function VoiceMeetingView({
  workspaceId,
  avatarUrlByName,
  status,
  meeting,
  segments,
  partial,
  contradictionAlerts,
  onClearContradictionAlert,
  audioQualityAlerts,
  onClearAudioQualityAlert,
  agendaReminder,
  onClearAgendaReminder,
  errorMessage,
  joinableMeeting,
  isViewer,
  onStart,
  onJoin,
  onPause,
  onResume,
  onStop,
  onLeave,
  onReset,
  onMapLiveSpeakers,
  onEditLiveSegment,
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
        avatarUrlByName={avatarUrlByName}
        liveStatus={status}
        liveMeeting={meeting}
        liveSegments={segments}
        livePartial={partial}
        liveContradictionAlerts={contradictionAlerts}
        onClearContradictionAlert={onClearContradictionAlert}
        liveAudioQualityAlerts={audioQualityAlerts}
        onClearAudioQualityAlert={onClearAudioQualityAlert}
        agendaReminder={agendaReminder}
        onClearAgendaReminder={onClearAgendaReminder}
        liveError={errorMessage}
        joinableMeeting={joinableMeeting}
        isViewer={isViewer}
        onStartLive={onStart}
        onJoinLive={onJoin}
        onPauseLive={onPause}
        onResumeLive={onResume}
        onStopLive={onStop}
        onLeaveLive={onLeave}
        onResetLive={onReset}
        onMapLiveSpeakers={onMapLiveSpeakers}
        onEditLiveSegment={onEditLiveSegment}
        onRenameLive={onRenameLive}
        t={t}
      />
    </div>
  );
}
