import { useState } from "react";
import { FAKE_STT_LINES } from "../data/fakeMeetingData";

export type MeetingStatus = "recording" | "paused" | "analyzing" | "ended";

export interface SpeakerStat {
  name: string;
  ms: number;
}

export interface VoiceMeeting {
  id: string;
  name: string;
  status: MeetingStatus;
  createdAt: number;
  accumulatedMs: number; // 지금까지 지난 재생 구간들의 누적 시간
  activeStartedAt: number | null; // 현재 재생 구간이 시작된 시각 (일시정지/종료면 null)
  summary: string | null; // 종료되면 채워짐 (더미)
  speakerStats: SpeakerStat[] | null; // 종료되면 채워짐 (더미) - 발화자별 발화 길이
  startedBy: string; // 누가 이 녹음을 시작했는지 - 지금은 더미로 순환 배정, 나중에 로그인 유저로 교체
}

interface WorkspaceMeetingState {
  meetings: VoiceMeeting[];
  activeMeetingId: string | null;
}

const EMPTY_STATE: WorkspaceMeetingState = { meetings: [], activeMeetingId: null };

const DUMMY_SUMMARY =
  "게이트웨이 통합안 논의, 세무사 대시보드와의 충돌 우려 제기. 다음 회의까지 검토하기로 함.";

// 실제 로그인 붙기 전까지, 녹음 시작할 때마다 이 순서대로 "시작한 사람"을 더미로 배정
const DEMO_PARTICIPANTS = ["지수", "나연", "승주", "동현"];

export function getElapsedMs(meeting: VoiceMeeting): number {
  if (meeting.status === "recording" && meeting.activeStartedAt) {
    return meeting.accumulatedMs + (Date.now() - meeting.activeStartedAt);
  }
  return meeting.accumulatedMs;
}

// 더미 발화자별 발화 시간 계산
function buildDummySpeakerStats(totalMs: number): SpeakerStat[] {
  const counts: Record<string, number> = {};
  FAKE_STT_LINES.forEach((line) => {
    counts[line.author] = (counts[line.author] ?? 0) + 1;
  });
  const totalLines = FAKE_STT_LINES.length;
  return Object.entries(counts).map(([name, count]) => ({
    name,
    ms: Math.round((totalMs * count) / totalLines),
  }));
}

// 매개변수 영역에 workspaceId와 함께 lang을 추가로 받아옵니다.
export function useVoiceMeetings(workspaceId: string, lang: string) {
  const [store, setStore] = useState<Record<string, WorkspaceMeetingState>>({});

  const current = store[workspaceId] ?? EMPTY_STATE;

  function updateState(updater: (prev: WorkspaceMeetingState) => WorkspaceMeetingState) {
    setStore((prev) => ({ ...prev, [workspaceId]: updater(prev[workspaceId] ?? EMPTY_STATE) }));
  }

  function startNewMeeting() {
    updateState((prev) => {
      const hasOngoing = prev.meetings.some((m) => m.status !== "ended");
      if (hasOngoing) return prev;

      const newMeeting: VoiceMeeting = {
        id: crypto.randomUUID(),
        // 외부 인자 lang을 판단하여 동적 할당 처리
        name: lang === "ko" 
          ? `회의 ${prev.meetings.length + 1}` 
          : `Meeting ${prev.meetings.length + 1}`,
        status: "recording",
        createdAt: Date.now(),
        accumulatedMs: 0,
        activeStartedAt: Date.now(),
        summary: null,
        speakerStats: null,
        startedBy: DEMO_PARTICIPANTS[prev.meetings.length % DEMO_PARTICIPANTS.length],
      };
      return { meetings: [newMeeting, ...prev.meetings], activeMeetingId: newMeeting.id };
    });
  }

  function pauseMeeting(id: string) {
    updateState((prev) => ({
      ...prev,
      meetings: prev.meetings.map((m) =>
        m.id === id && m.status === "recording"
          ? {
              ...m,
              status: "paused",
              accumulatedMs: m.accumulatedMs + (m.activeStartedAt ? Date.now() - m.activeStartedAt : 0),
              activeStartedAt: null,
            }
          : m
      ),
    }));
  }

  function resumeMeeting(id: string) {
    updateState((prev) => ({
      ...prev,
      meetings: prev.meetings.map((m) =>
        m.id === id && m.status === "paused" ? { ...m, status: "recording", activeStartedAt: Date.now() } : m
      ),
    }));
  }

  function stopMeeting(id: string) {
    updateState((prev) => ({
      ...prev,
      meetings: prev.meetings.map((m) => {
        if (m.id !== id) return m;
        const finalMs = m.accumulatedMs + (m.activeStartedAt ? Date.now() - m.activeStartedAt : 0);
        return { ...m, status: "analyzing", accumulatedMs: finalMs, activeStartedAt: null };
      }),
    }));

    setTimeout(() => {
      updateState((prev) => ({
        ...prev,
        meetings: prev.meetings.map((m) =>
          m.id === id
            ? {
                ...m,
                status: "ended",
                summary: DUMMY_SUMMARY,
                speakerStats: buildDummySpeakerStats(m.accumulatedMs),
              }
            : m
        ),
      }));
    }, 1800);
  }

  function renameMeeting(id: string, name: string) {
    updateState((prev) => ({
      ...prev,
      meetings: prev.meetings.map((m) => (m.id === id ? { ...m, name } : m)),
    }));
  }

  function selectMeeting(id: string | null) {
    updateState((prev) => ({ ...prev, activeMeetingId: id }));
  }

  return {
    meetings: current.meetings,
    activeMeetingId: current.activeMeetingId,
    startNewMeeting,
    pauseMeeting,
    resumeMeeting,
    stopMeeting,
    renameMeeting,
    selectMeeting,
  };
}