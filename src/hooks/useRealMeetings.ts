import { useEffect, useState } from "react";
import {
  Meeting,
  MeetingSegment,
  MeetingSummary,
  Decision,
  getMeetingListApi,
  deleteMeetingApi,
  getMeetingSegmentsApi,
  getMeetingSummaryApi,
  getMeetingDecisionsApi,
  uploadMeetingAudioApi,
  mapSpeakerNamesApi,
  renameMeetingApi,
} from "../services/meeting";

const PENDING_STATUSES = new Set(["created", "processing"]);

// 업로드된 회의(STT 요약/결정사항) 실제 백엔드 연동
export function useRealMeetings(workspaceId: string) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [segments, setSegments] = useState<MeetingSegment[]>([]);
  const [summary, setSummary] = useState<MeetingSummary | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const selectedMeeting = meetings.find((m) => m.id === selectedMeetingId) ?? null;

  async function loadMeetings() {
    if (!workspaceId) return;
    const res = await getMeetingListApi(workspaceId);
    if (res.status === "success") {
      setMeetings(res.meetings);
    }
  }

  useEffect(() => {
    setSelectedMeetingId(null);
    setIsLoading(true);
    loadMeetings().finally(() => setIsLoading(false));
  }, [workspaceId]);

  // 아직 STT/후처리 중인 회의가 있으면 완료될 때까지 목록을 주기적으로 재조회
  useEffect(() => {
    const hasPending = meetings.some((m) => PENDING_STATUSES.has(m.status));
    if (!hasPending) return;
    const timer = setInterval(loadMeetings, 5000);
    return () => clearInterval(timer);
  }, [meetings, workspaceId]);

  useEffect(() => {
    async function loadDetail() {
      if (!workspaceId || !selectedMeetingId) {
        setSegments([]);
        setSummary(null);
        setDecisions([]);
        return;
      }

      setIsDetailLoading(true);
      const [segRes, sumRes, decRes] = await Promise.all([
        getMeetingSegmentsApi(workspaceId, selectedMeetingId),
        getMeetingSummaryApi(workspaceId, selectedMeetingId),
        getMeetingDecisionsApi(workspaceId, selectedMeetingId),
      ]);
      setIsDetailLoading(false);

      setSegments(segRes.status === "success" ? segRes.segments : []);
      setSummary(sumRes.status === "success" ? sumRes.summary : null);
      setDecisions(decRes.status === "success" ? decRes.decisions : []);
    }

    loadDetail();
  }, [workspaceId, selectedMeetingId, selectedMeeting?.status]);

  async function uploadAudio(file: File, title: string) {
    setIsUploading(true);
    const res = await uploadMeetingAudioApi(workspaceId, file, title);
    setIsUploading(false);

    if (res.status === "success" && res.meeting) {
      setMeetings((prev) => [res.meeting as Meeting, ...prev]);
      setSelectedMeetingId(res.meeting.id);
    } else {
      alert(`음성 업로드 실패: ${res.message}`);
    }
  }

  async function mapSpeakerNames(mapping: Record<string, string>) {
    if (!selectedMeetingId) return;
    const res = await mapSpeakerNamesApi(workspaceId, selectedMeetingId, mapping);
    if (res.status === "success") {
      setSegments((prev) =>
        prev.map((s) =>
          s.speaker_label && res.speakerLabels[s.speaker_label]
            ? { ...s, speaker_label: res.speakerLabels[s.speaker_label] }
            : s
        )
      );
    } else {
      alert(`화자 이름 지정 실패: ${res.message}`);
    }
  }

  async function renameMeeting(id: string, title: string) {
    const res = await renameMeetingApi(workspaceId, id, title);
    if (res.status === "success" && res.meeting) {
      const updated = res.meeting;
      setMeetings((prev) => prev.map((m) => (m.id === id ? updated : m)));
    } else {
      alert(`회의 제목 변경 실패: ${res.message}`);
    }
  }

  async function removeMeeting(id: string) {
    const res = await deleteMeetingApi(workspaceId, id);

    if (res.status === "success") {
      setMeetings((prev) => prev.filter((m) => m.id !== id));
      setSelectedMeetingId((prev) => (prev === id ? null : prev));
    } else {
      alert(`회의 삭제 실패: ${res.message}`);
    }
  }

  return {
    meetings,
    isLoading,
    selectedMeetingId,
    setSelectedMeetingId,
    selectedMeeting,
    segments,
    summary,
    decisions,
    isDetailLoading,
    isUploading,
    uploadAudio,
    removeMeeting,
    renameMeeting,
    mapSpeakerNames,
    reload: loadMeetings,
  };
}
