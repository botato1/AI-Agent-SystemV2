// src/types.ts

// 카테고리 계층 없이 채팅방(채널) 하나하나가 사이드바에 바로 나열되는 구조로 변경
export interface Channel {
  id: string;
  name: string;
}

// 워크스페이스 - 사이드바 맨 위 이름, 여러 개 만들고 전환 가능
export interface Workspace {
  id: string;
  name: string;
}

// 채팅방 안 "메시지" 탭에 표시되는 팀원별 최근 활동 한 줄
export interface MemberActivity {
  name: string;
  preview: string; // 최근 메시지/업로드/분석 내용 미리보기
  kind: "message" | "upload" | "ai"; // 말풍선 여러 줄 / 문서 업로드 / AI 분석 결과 구분
  isAi?: boolean;
}

export interface User {
  id: string;
  name: string;
  username: string; // 로그인용 아이디 (중복 불가)
  status: "online" | "away" | "offline";
  avatarColor: string; // 프로필 동그라미 색상
  avatarImageUrl: string | null; // 직접 업로드한 사진
}

// 대시보드 - 할 일 (칸반보드)
export type TaskStatus = "todo" | "in_progress" | "done" | "delayed";
export type TaskPriority = "high" | "medium" | "low";

export interface Task {
  id: string;
  task: string;
  assignee: string | null;
  deadline: string | null; // "YYYY-MM-DD"
  status: TaskStatus;
  priority: TaskPriority;
}

// 대시보드 - 모순 감지 로그
export interface ContradictionLogEntry {
  id: string;
  channelName: string;
  description: string;
  status: "pending" | "kept" | "changed";
  date: string;
}

// [핵심 교정] 훅과 뷰 컴포넌트 전체가 사용하는 규격에 맞게 "analyzed"로 통일합니다.
export type DocumentAnalysisStatus = "analyzing" | "analyzed";

export interface AnalyzedDocument {
  id: string;
  name: string;
  size: number;
  uploadedAt: number;
  status: DocumentAnalysisStatus;
  summary: string | null; // 분석 끝나면 채워짐
  keywords: string[] | null; // 분석 끝나면 채워짐
  fileType: string; // 원본 미리보기용 mime 타입
  fileUrl: string; // 임시 URL
}