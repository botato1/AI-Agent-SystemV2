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
// (다른 팀원이 녹음 중인 상황도 데모로 보여주기 위함 - 나중엔 진짜 로그인 유저 이름으로 교체하면 됨)
const DEMO_PARTICIPANTS = ["지수", "나연", "승주", "동현"];

export function getElapsedMs(meeting: VoiceMeeting): number {
  if (meeting.status === "recording" && meeting.activeStartedAt) {
    return meeting.accumulatedMs + (Date.now() - meeting.activeStartedAt);
  }
  return meeting.accumulatedMs;
}

// 더미 발화자별 발화 시간 계산 - 전체 스크립트에서 각 화자가 말한 줄 수 비율대로 총 시간을 나눔
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

// workspaceId별로 회의 목록을 독립적으로 저장 - 워크스페이스를 바꿔도 서로 안 섞임
// (useChannelRuntime이 채널별로 채팅을 분리하는 것과 같은 패턴)
export function useVoiceMeetings(workspaceId: string) {
  const [store, setStore] = useState<Record<string, WorkspaceMeetingState>>({});

  const current = store[workspaceId] ?? EMPTY_STATE;

  function updateState(updater: (prev: WorkspaceMeetingState) => WorkspaceMeetingState) {
    setStore((prev) => ({ ...prev, [workspaceId]: updater(prev[workspaceId] ?? EMPTY_STATE) }));
  }

  // 이미 진행 중인(녹음중/일시정지/분석중) 회의가 있으면 새로 시작 안 함 - UI에서 버튼을 막아두긴 하지만,
  // 혹시 모를 경우를 대비해 훅 레벨에서도 한 번 더 방어
  function startNewMeeting() {
    updateState((prev) => {
      const hasOngoing = prev.meetings.some((m) => m.status !== "ended");
      if (hasOngoing) return prev;

      const newMeeting: VoiceMeeting = {
        id: crypto.randomUUID(),
        name: `회의 ${prev.meetings.length + 1}`,
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

  // 녹음을 끝내면 바로 결과가 나오는 게 아니라, 실제로 STT/화자분리/요약에 시간이 걸리는 걸
  // 흉내내기 위해 잠깐 "분석 중" 상태를 거친 다음 결과가 채워짐 (나중에 실제 API 붙일 때도 이 흐름 그대로 씀)
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