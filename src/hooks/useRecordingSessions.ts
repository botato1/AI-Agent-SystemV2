import { useState } from "react";

export type RecordingStatus = "recording" | "paused" | "ended";

export interface RecordingSession {
  id: string;
  name: string;
  status: RecordingStatus;
  createdAt: number;
  accumulatedMs: number;
  activeStartedAt: number | null;
  summary: string | null;
}

const DUMMY_SUMMARY =
  "게이트웨이 통합안 논의, 세무사 대시보드와의 충돌 우려 제기. 다음 회의까지 검토하기로 함.";

export function getElapsedMs(session: RecordingSession): number {
  if (session.status === "recording" && session.activeStartedAt) {
    return session.accumulatedMs + (Date.now() - session.activeStartedAt);
  }
  return session.accumulatedMs;
}

export function useRecordingSessions() {
  const [sessions, setSessions] = useState<RecordingSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  function startNewRecording() {
    const newSession: RecordingSession = {
      id: crypto.randomUUID(),
      name: `녹음 ${sessions.length + 1}`,
      status: "recording",
      createdAt: Date.now(),
      accumulatedMs: 0,
      activeStartedAt: Date.now(),
      summary: null,
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  }

  function pauseRecording(id: string) {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id && s.status === "recording"
          ? {
              ...s,
              status: "paused",
              accumulatedMs: s.accumulatedMs + (s.activeStartedAt ? Date.now() - s.activeStartedAt : 0),
              activeStartedAt: null,
            }
          : s
      )
    );
  }

  function resumeRecording(id: string) {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id && s.status === "paused"
          ? { ...s, status: "recording", activeStartedAt: Date.now() }
          : s
      )
    );
  }

  function stopRecording(id: string) {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id
          ? {
              ...s,
              status: "ended",
              accumulatedMs: s.accumulatedMs + (s.activeStartedAt ? Date.now() - s.activeStartedAt : 0),
              activeStartedAt: null,
              summary: DUMMY_SUMMARY,
            }
          : s
      )
    );
  }

  function renameRecording(id: string, name: string) {
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, name } : s)));
  }

  return {
    sessions,
    activeSessionId,
    setActiveSessionId,
    startNewRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    renameRecording,
  };
}