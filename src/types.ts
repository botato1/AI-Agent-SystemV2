// src/types.ts

// 카테고리 계층 없이 채팅방(채널) 하나하나가 사이드바에 바로 나열되는 구조로 변경
// (category_id는 워크스페이스 전역 카테고리 선택기로 필터링하기 위한 것으로, 위 계층 구조와는 다르다)
export interface Channel {
  id: string;
  name: string;
  category_id?: string | null;
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
export type TaskStatus = "todo" | "in_progress" | "done" | "cancelled";
export type TaskPriority = "high" | "medium" | "low";

export interface Task {
  id: string;
  task: string;
  description?: string | null;
  assignee: string | null;
  deadline: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  category_id?: string | null;
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
export type DocumentAnalysisStatus = "analyzing" | "analyzed" | "failed";

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
  category_id?: string | null;
}

export interface Workspace {
  id: string;
  name: string;
  description?: string | null; 
  owner_id?: string;         
  created_at?: string;      
}

// 워크스페이스 목록 조회 API 전체 응답 타입 
export interface WorkspaceListApiResponse {
  status: "success" | "error";
  workspaces: Workspace[]; // 배열 형태
  error: string | null;
}

export type PlaceholderKey = "home" | "dashboard" | "docAnalysis" | "voiceMeeting" | "graph" | "aiChat";