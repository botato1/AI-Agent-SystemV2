import { Channel, ContradictionLogEntry, MemberActivity, Task, User, Workspace } from "../types";

// 워크스페이스 목록 (더미) - 사이드바 맨 위 이름 눌러서 전환/생성
export const mockWorkspaces: Workspace[] = [{ id: "ws-1", name: "비트 프로젝트" }];

// 지금은 하드코딩된 목업 데이터. 나중에 실제 API 연동 시 이 구조 그대로 백엔드 응답에 맞춰 교체하면 됨
// 카테고리 계층 없이 채팅방(채널)이 사이드바에 바로 나열됨
export const mockChannels: Channel[] = [
  { id: "ch-1", name: "채팅방 1" },
  { id: "ch-2", name: "채팅방 2" },
  { id: "ch-3", name: "채팅방 3" },
];

// 채팅방 "메시지" 탭 왼쪽에 보이는 팀원별 최근 활동 (더미)
export const mockMemberActivities: MemberActivity[] = [
  { name: "지수", preview: "API 게이트웨이 통합안 정리해서 올렸어요", kind: "message" },
  { name: "나연", preview: "확인했습니다, 오늘 회의 때 다시 얘기해요", kind: "message" },
  { name: "승주", preview: "문서 업로드", kind: "upload" },
  { name: "AI Bot", preview: "분석 내용 보기", kind: "ai", isAi: true },
];

// 대시보드 - 할 일 (더미)
export const mockTasks: Task[] = [
  {
    id: "task-1",
    task: "게이트웨이 통합안 문서화",
    assignee: "지수",
    deadline: "2026-07-18",
    status: "todo",
    priority: "high",
  },
  {
    id: "task-2",
    task: "세무사 대시보드 충돌 여부 재확인",
    assignee: "나연",
    deadline: "2026-07-16",
    status: "in_progress",
    priority: "high",
  },
  {
    id: "task-3",
    task: "LangGraph 노드 연동 검토",
    assignee: "동현",
    deadline: null,
    status: "done",
    priority: "medium",
  },
  {
    id: "task-4",
    task: "STT 정확도 테스트",
    assignee: "준오",
    deadline: "2026-07-14",
    status: "delayed",
    priority: "medium",
  },
];

// 대시보드 - 모순 감지 로그 (더미)
export const mockContradictionLog: ContradictionLogEntry[] = [
  {
    id: "log-1",
    channelName: "채팅방 1",
    description: '지수님 "게이트웨이 하나로 통합" vs 승주님 문서 "게이트웨이 분리"',
    status: "pending",
    date: "7/13",
  },
  {
    id: "log-2",
    channelName: "채팅방 2",
    description: "페르소나 정의가 지난주 회의와 다르게 변경됨",
    status: "changed",
    date: "7/11",
  },
  {
    id: "log-3",
    channelName: "채팅방 1",
    description: "STT 정확도 목표치가 두 문서에서 다르게 명시됨",
    status: "kept",
    date: "7/9",
  },
];