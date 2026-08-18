// src/components/MeetingAudioPlayer.tsx
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { getMeetingAudioApi } from "../services/meeting";
import { MicIcon } from "./icons";

interface Props {
  workspaceId: string;
  meetingId: string;
  t: any;
}

export interface MeetingAudioPlayerHandle {
  seekTo: (timeMs: number) => void;
}

// 회의 원본 음성 재생 - Authorization 헤더가 필요해서 <audio src="..."> 대신
// fetch로 Blob을 받아 object URL을 만들어서 재생한다.
const MeetingAudioPlayer = forwardRef<MeetingAudioPlayerHandle, Props>(function MeetingAudioPlayer(
  { workspaceId, meetingId, t },
  ref
) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  useImperativeHandle(ref, () => ({
    seekTo(timeMs: number) {
      const audio = audioRef.current;
      if (!audio) return;
      audio.currentTime = timeMs / 1000;
      audio.play().catch(() => {});
    },
  }));

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setIsLoading(true);
    setErrorMsg(null);
    setAudioUrl(null);

    async function load() {
      const res = await getMeetingAudioApi(workspaceId, meetingId);
      if (cancelled) return;

      if (res.status === "success" && res.blob) {
        objectUrl = URL.createObjectURL(res.blob);
        setAudioUrl(objectUrl);
      } else {
        setErrorMsg(res.message);
      }
      setIsLoading(false);
    }

    load();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [workspaceId, meetingId]);

  if (isLoading) {
    return <p className="text-xs text-recall-textMuted">{t.meeting_audio_loading}</p>;
  }

  if (errorMsg || !audioUrl) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-recall-textMuted">
        <MicIcon size={13} className="flex-shrink-0" />
        <span>{errorMsg || t.meeting_audio_unavailable}</span>
      </div>
    );
  }

  return <audio ref={audioRef} controls src={audioUrl} className="h-9 w-full max-w-sm" />;
});

export default MeetingAudioPlayer;
