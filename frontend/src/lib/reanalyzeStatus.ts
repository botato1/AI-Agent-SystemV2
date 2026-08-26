import { useEffect, useState } from "react";

// 재분석 진행 중인 회의 id 집합 - 컴포넌트 트리와 무관한 모듈 전역 상태로 관리한다
// (lib/toast.tsx, lib/confirm.tsx와 동일 패턴). 다른 페이지로 이동했다 돌아와도
// MeetingsPanel이 다시 마운트될 때 이 상태를 그대로 이어받아 스피너가 끊기지 않는다.
let reanalyzingIds = new Set<string>();
const listeners = new Set<(ids: Set<string>) => void>();

function emit() {
  listeners.forEach((listener) => listener(reanalyzingIds));
}

export function markReanalyzing(meetingId: string) {
  if (reanalyzingIds.has(meetingId)) return;
  reanalyzingIds = new Set(reanalyzingIds).add(meetingId);
  emit();
}

export function markReanalyzeDone(meetingId: string) {
  if (!reanalyzingIds.has(meetingId)) return;
  const next = new Set(reanalyzingIds);
  next.delete(meetingId);
  reanalyzingIds = next;
  emit();
}

export function useReanalyzingMeetingIds(): Set<string> {
  const [ids, setIds] = useState(reanalyzingIds);

  useEffect(() => {
    listeners.add(setIds);
    return () => {
      listeners.delete(setIds);
    };
  }, []);

  return ids;
}
