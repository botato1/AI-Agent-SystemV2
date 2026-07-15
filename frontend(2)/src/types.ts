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
  name: string;
  username: string; // 로그인용 아이디 (중복 불가)
  status: "online" | "away" | "offline";
  avatarColor: string; // 프로필 동그라미 색상 (회원가입 때 고르거나, 안 고르면 랜덤 배정)
  avatarImageUrl: string | null; // 직접 업로드한 사진 - 있으면 색상 대신 이걸 보여줌
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

// 대시보드 - 모순 감지 로그 (채널별 회의/채팅에서 감지된 모순 이력)
export interface ContradictionLogEntry {
  id: string;
  channelName: string;
  description: string;
  status: "pending" | "kept" | "changed";
  date: string;
}

// 문서 분석
export type DocumentAnalysisStatus = "analyzing" | "done";

export interface AnalyzedDocument {
  id: string;
  name: string;
  size: number;
  uploadedAt: number;
  status: DocumentAnalysisStatus;
  summary: string | null; // 분석 끝나면 채워짐 (더미)
  keywords: string[] | null; // 분석 끝나면 채워짐 (더미)
  fileType: string; // 원본 미리보기 방식을 결정하는 mime 타입 (예: application/pdf, image/png)
  fileUrl: string; // URL.createObjectURL로 만든 임시 URL - 원본 보기/다운로드용
}