import { useState } from "react";

export type RecordingStatus = "recording" | "paused" | "ended";

export interface Recording {
  id: string;
  name: string;
  status: RecordingStatus;
  createdAt: number;
  // 일시정지를 거쳐도 "실제로 녹음된 시간"만 정확히 계산하기 위한 값들
  accumulatedMs: number; // 지금까지 지난 재생 구간들의 누적 시간
  activeStartedAt: number | null; // 현재 재생 구간이 시작된 시각 (일시정지/종료 상태면 null)
  // 종료되면 채워짐 (지금은 전부 더미 고정 텍스트, 나중에 AI 분석 API로 교체)
  oneLineSummary: string | null;
  summary: string | null;
  keywords: string[] | null;
  actionItems: string[] | null;
}

interface CategoryRecordingState {
  recordings: Recording[];
  activeRecordingId: string | null;
}

const DUMMY_ONE_LINE_SUMMARY = "게이트웨이 통합안을 논의하고 다음 회의까지 검토하기로 함";

const DUMMY_SUMMARY =
  "게이트웨이 통합안 논의, 세무사 대시보드와의 충돌 우려 제기. 다음 회의까지 검토하기로 함.";

const DUMMY_KEYWORDS = ["API 게이트웨이", "세무사 대시보드", "충돌 검토", "LangGraph"];

const DUMMY_ACTION_ITEMS = [
  "동현 - LangGraph 노드 연동 검토",
  "지수 - 게이트웨이 통합안 문서화",
  "나연 - 세무사 대시보드 충돌 여부 재확인",
];

const EMPTY_STATE: CategoryRecordingState = { recordings: [], activeRecordingId: null };

// 지금 이 순간 기준 "실제 녹음된 시간(ms)" - 일시정지된 시간은 흐르지 않음
export function getElapsedMs(recording: Recording): number {
  if (recording.status === "recording" && recording.activeStartedAt) {
    return recording.accumulatedMs + (Date.now() - recording.activeStartedAt);
  }
  return recording.accumulatedMs;
}

// 카테고리 id별로 녹음 목록/진행 상태를 독립 관리. App 최상단에서 한 번만 생성해서
// 카테고리를 넘나들거나 화면을 전환해도(음성 허브 <-> 채널) 상태가 유지되도록 함
export function useCategoryRecordings() {
  const [store, setStore] = useState<Record<string, CategoryRecordingState>>({});

  function getState(categoryId: string): CategoryRecordingState {
    return store[categoryId] ?? EMPTY_STATE;
  }

  function updateState(
    categoryId: string,
    updater: (prev: CategoryRecordingState) => CategoryRecordingState
  ) {
    setStore((prev) => ({ ...prev, [categoryId]: updater(prev[categoryId] ?? EMPTY_STATE) }));
  }

  function startNewRecording(categoryId: string) {
    updateState(categoryId, (prev) => {
      const newRecording: Recording = {
        id: crypto.randomUUID(),
        name: `녹음 ${prev.recordings.length + 1}`,
        status: "recording",
        createdAt: Date.now(),
        accumulatedMs: 0,
        activeStartedAt: Date.now(),
        oneLineSummary: null,
        summary: null,
        keywords: null,
        actionItems: null,
      };
      return { recordings: [newRecording, ...prev.recordings], activeRecordingId: newRecording.id };
    });
  }

  // 일시정지: 세션은 그대로 두고, 지금까지 지난 시간만 누적값에 더해둠 (새 녹음 아님)
  function pauseRecording(categoryId: string, recordingId: string) {
    updateState(categoryId, (prev) => ({
      ...prev,
      recordings: prev.recordings.map((r) =>
        r.id === recordingId && r.status === "recording"
          ? {
              ...r,
              status: "paused",
              accumulatedMs: r.accumulatedMs + (r.activeStartedAt ? Date.now() - r.activeStartedAt : 0),
              activeStartedAt: null,
            }
          : r
      ),
    }));
  }

  // 재개: 같은 세션에서 재생 구간만 다시 시작 (새 녹음 아님)
  function resumeRecording(categoryId: string, recordingId: string) {
    updateState(categoryId, (prev) => ({
      ...prev,
      recordings: prev.recordings.map((r) =>
        r.id === recordingId && r.status === "paused"
          ? { ...r, status: "recording", activeStartedAt: Date.now() }
          : r
      ),
    }));
  }

  function stopRecording(categoryId: string, recordingId: string) {
    updateState(categoryId, (prev) => ({
      recordings: prev.recordings.map((r) =>
        r.id === recordingId
          ? {
              ...r,
              status: "ended",
              accumulatedMs: r.accumulatedMs + (r.activeStartedAt ? Date.now() - r.activeStartedAt : 0),
              activeStartedAt: null,
              oneLineSummary: DUMMY_ONE_LINE_SUMMARY,
              summary: DUMMY_SUMMARY,
              keywords: DUMMY_KEYWORDS,
              actionItems: DUMMY_ACTION_ITEMS,
            }
          : r
      ),
      activeRecordingId: prev.activeRecordingId === recordingId ? null : prev.activeRecordingId,
    }));
  }

  function renameRecording(categoryId: string, recordingId: string, name: string) {
    updateState(categoryId, (prev) => ({
      ...prev,
      recordings: prev.recordings.map((r) => (r.id === recordingId ? { ...r, name } : r)),
    }));
  }

  function selectRecording(categoryId: string, recordingId: string | null) {
    updateState(categoryId, (prev) => ({ ...prev, activeRecordingId: recordingId }));
  }

  return {
    getState,
    startNewRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    renameRecording,
    selectRecording,
  };
}