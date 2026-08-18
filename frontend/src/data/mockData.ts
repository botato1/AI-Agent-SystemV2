// src/data/mockData.ts
import { Channel, ContradictionLogEntry, Task, Workspace } from "../types";
import { Language } from "./translations";

export function getMockData(lang: Language) {
  const isKo = lang === "ko";

  const mockWorkspaces: Workspace[] = [
    { id: "ws-1", name: isKo ? "비트 프로젝트" : "BIT Project" }
  ];

  const mockChannels: Channel[] = [
    { id: "ch-1", name: isKo ? "채팅방 1" : "Chatroom 1" },
    { id: "ch-2", name: isKo ? "채팅방 2" : "Chatroom 2" },
    { id: "ch-3", name: isKo ? "채팅방 3" : "Chatroom 3" },
  ];

  const mockTasks: Task[] = [
    {
      id: "task-1",
      task: isKo ? "게이트웨이 통합안 문서화" : "Documenting API Gateway integration plan",
      assignee: isKo ? "지수" : "Jisu",
      deadline: "2026-07-18",
      status: "todo",
      priority: "high",
    },
    {
      id: "task-2",
      task: isKo ? "세무사 대시보드 충돌 여부 재확인" : "Double-checking tax accountant dashboard conflict",
      assignee: isKo ? "나연" : "Nayeon",
      deadline: "2026-07-16",
      status: "in_progress",
      priority: "high",
    },
    {
      id: "task-3",
      task: isKo ? "LangGraph 노드 연동 검토" : "Reviewing LangGraph node connection",
      assignee: isKo ? "동현" : "Donghyun",
      deadline: null,
      status: "done",
      priority: "medium",
    },
    {
      id: "task-4",
      task: isKo ? "STT 정확도 테스트" : "Testing STT accuracy",
      assignee: isKo ? "준오" : "Juno",
      deadline: "2026-07-14",
      status: "cancelled",
      priority: "medium",
    },
  ];

  const mockContradictionLog: ContradictionLogEntry[] = [
    {
      id: "log-1",
      channelName: isKo ? "채팅방 1" : "Chatroom 1",
      description: isKo 
        ? '지수님 "게이트웨이 하나로 통합" vs 승주님 문서 "게이트웨이 분리"'
        : 'Jisu "Integrate API Gateway" vs Seungju document "Separate API Gateway"',
      status: "pending",
      date: "7/13",
    },
    {
      id: "log-2",
      channelName: isKo ? "채팅방 2" : "Chatroom 2",
      description: isKo
        ? "페르소나 정의가 지난주 회의와 다르게 변경됨"
        : "Persona definition changed from last week's meeting",
      status: "changed",
      date: "7/11",
    },
    {
      id: "log-3",
      channelName: isKo ? "채팅방 1" : "Chatroom 1",
      description: isKo
        ? "STT 정확도 목표치가 두 문서에서 다르게 명시됨"
        : "STT accuracy target specified differently in two documents",
      status: "kept",
      date: "7/9",
    },
  ];

  return {
    mockWorkspaces,
    mockChannels,
    mockTasks,
    mockContradictionLog,
  };
}