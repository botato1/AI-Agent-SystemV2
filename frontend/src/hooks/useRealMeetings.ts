import { useEffect, useRef, useState } from "react";
import {
  Meeting,
  MeetingSegment,
  MeetingSummary,
  Decision,
  MeetingAttendee,
  MeetingDocumentItem,
  SplitSegmentParams,
  getMeetingListApi,
  deleteMeetingApi,
  getMeetingSegmentsApi,
  getMeetingSummaryApi,
  getMeetingDecisionsApi,
  createMeetingDecisionApi,
  updateMeetingDecisionApi,
  getMeetingAttendeesApi,
  getMeetingDocumentsApi,
  deleteMeetingDocumentApi,
  uploadMeetingAudioApi,
  mapSpeakerNamesApi,
  updateMeetingSegmentApi,
  splitMeetingSegmentApi,
  updateMeetingSummaryApi,
  renameMeetingApi,
  updateMeetingInfoApi,
} from "../services/meeting";
import { BackendTask, getSuggestedTasksApi, updateTaskStatusApi, deleteTaskApi } from "../services/task";
import { useNotifications } from "./useNotifications";

// 업로드된 회의(STT 요약/결정사항) 실제 백엔드 연동
export function useRealMeetings(workspaceId: string, selectedCategoryId?: string | null) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(null);
  const [segments, setSegments] = useState<MeetingSegment[]>([]);
  const [summary, setSummary] = useState<MeetingSummary | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [attendees, setAttendees] = useState<MeetingAttendee[]>([]);
  const [documents, setDocuments] = useState<MeetingDocumentItem[]>([]);
  const [suggestedTasks, setSuggestedTasks] = useState<BackendTask[]>([]);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const selectedMeeting = meetings.find((m) => m.id === selectedMeetingId) ?? null;

  async function loadMeetings() {
    if (!workspaceId) return;
    const res = await getMeetingListApi(workspaceId);
    if (res.status === "success") {
      setMeetings(res.meetings);
      return;
    }
    // 조용히 실패하고 끝나면(네트워크 순단 등) 목록이 그대로 멈춰버리니 한 번은 재시도한다.
    setTimeout(async () => {
      const retryRes = await getMeetingListApi(workspaceId);
      if (retryRes.status === "success") setMeetings(retryRes.meetings);
    }, 2000);
  }

  useEffect(() => {
    setSelectedMeetingId(null);
    setIsLoading(true);
    loadMeetings().finally(() => setIsLoading(false));
  }, [workspaceId]);

  // 사이드바에서 카테고리를 바꾸면 지금 보던 회의가 새 카테고리에 없을 수 있으니, 상세 패널을
  // 열어둔 채로 다른 카테고리 회의가 계속 보이지 않게 선택을 초기화한다.
  useEffect(() => {
    setSelectedMeetingId(null);
  }, [selectedCategoryId]);

  // 목록을 주기적으로 재조회 - 다른 팀원이 새로 시작한 회의는 내 로컬 목록에 아직 없어서
  // "진행 중인 회의가 있을 때만" 폴링하는 조건으로는 절대 못 잡는다(새로고침해야만 보이던
  // 원인). 그래서 이 페이지를 보고 있는 동안엔 로컬 목록 상태와 무관하게 항상 폴링한다.
  useEffect(() => {
    if (!workspaceId) return;
    const timer = setInterval(loadMeetings, 5000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  async function loadDetail() {
    if (!workspaceId || !selectedMeetingId) {
      setSegments([]);
      setSummary(null);
      setDecisions([]);
      setAttendees([]);
      setSuggestedTasks([]);
      setDocuments([]);
      return;
    }

    setIsDetailLoading(true);
    const [segRes, sumRes, decRes, attRes, suggestedRes, docRes] = await Promise.all([
      getMeetingSegmentsApi(workspaceId, selectedMeetingId),
      getMeetingSummaryApi(workspaceId, selectedMeetingId),
      getMeetingDecisionsApi(workspaceId, selectedMeetingId),
      getMeetingAttendeesApi(workspaceId, selectedMeetingId),
      getSuggestedTasksApi(workspaceId, selectedMeetingId),
      getMeetingDocumentsApi(workspaceId, selectedMeetingId),
    ]);
    setIsDetailLoading(false);

    setSegments(segRes.status === "success" ? segRes.segments : []);
    setSummary(sumRes.status === "success" ? sumRes.summary : null);
    setDecisions(decRes.status === "success" ? decRes.decisions : []);
    setAttendees(attRes.status === "success" ? attRes.attendees : []);
    setSuggestedTasks(suggestedRes.status === "success" ? suggestedRes.tasks : []);
    setDocuments(docRes.status === "success" ? docRes.documents : []);
  }

  useEffect(() => {
    loadDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, selectedMeetingId, selectedMeeting?.status]);

  // 같은 회의를 다른 팀원과 같이 보고 있을 때 결정사항/참석자/첨부문서/추천 할 일이
  // 새로고침 없이 반영되도록 백그라운드에서 조용히 재조회한다. segments/summary는
  // 일부러 뺐다 - "전체 요약 수정"/"발화 일괄 수정" 중인 텍스트 draft가 prop이 바뀔 때마다
  // useEffect로 덮어써지는 구조라(EditableFullSummary 등), 여기서 건드리면 입력 중인
  // 내용이 통째로 날아간다.
  useEffect(() => {
    if (!workspaceId || !selectedMeetingId) return;

    async function pollSecondaryDetail() {
      const [decRes, attRes, suggestedRes, docRes] = await Promise.all([
        getMeetingDecisionsApi(workspaceId, selectedMeetingId!),
        getMeetingAttendeesApi(workspaceId, selectedMeetingId!),
        getSuggestedTasksApi(workspaceId, selectedMeetingId!),
        getMeetingDocumentsApi(workspaceId, selectedMeetingId!),
      ]);
      setDecisions(decRes.status === "success" ? decRes.decisions : []);
      setAttendees(attRes.status === "success" ? attRes.attendees : []);
      setSuggestedTasks(suggestedRes.status === "success" ? suggestedRes.tasks : []);
      setDocuments(docRes.status === "success" ? docRes.documents : []);
    }

    const timer = setInterval(pollSecondaryDetail, 8000);
    return () => clearInterval(timer);
  }, [workspaceId, selectedMeetingId]);

  // 정밀 재분석으로 요약이 갱신되면 서버가 ref_type="meeting", ref_id=meeting_id인
  // meeting_summary_ready 알림을 보낸다 - 지금 보고 있는 회의 것이면 요약을 다시 받아온다.
  const { notifications } = useNotifications(workspaceId);
  const handledSummaryNotificationIdsRef = useRef(new Set<string>());
  // "재분석" 버튼을 누른 뒤 이 알림이 와야 실제로 끝난 걸 아는데, 훅 바깥(버튼이 있는
  // 컴포넌트)에서도 그 시점을 알 수 있게 갱신될 때마다 타임스탬프를 노출해둔다.
  const [summaryRefreshedAt, setSummaryRefreshedAt] = useState<number | null>(null);

  useEffect(() => {
    if (!workspaceId || !selectedMeetingId) return;

    const pending = notifications.filter(
      (n) =>
        n.type === "meeting_summary_ready" &&
        n.ref_type === "meeting" &&
        n.ref_id === selectedMeetingId &&
        !handledSummaryNotificationIdsRef.current.has(n.id)
    );
    if (pending.length === 0) return;

    pending.forEach((n) => handledSummaryNotificationIdsRef.current.add(n.id));

    getMeetingSummaryApi(workspaceId, selectedMeetingId).then((res) => {
      if (res.status === "success") setSummary(res.summary);
      setSummaryRefreshedAt(Date.now());
    });
  }, [notifications, workspaceId, selectedMeetingId]);

  async function reloadAttendees() {
    if (!workspaceId || !selectedMeetingId) return;
    const res = await getMeetingAttendeesApi(workspaceId, selectedMeetingId);
    if (res.status === "success") setAttendees(res.attendees);
  }

  async function reloadDocuments() {
    if (!workspaceId || !selectedMeetingId) return;
    const res = await getMeetingDocumentsApi(workspaceId, selectedMeetingId);
    if (res.status === "success") setDocuments(res.documents);
  }

  async function removeDocument(documentId: string) {
    if (!selectedMeetingId) return;
    const res = await deleteMeetingDocumentApi(workspaceId, selectedMeetingId, documentId);
    if (res.status === "success") {
      setDocuments((prev) => prev.filter((d) => d.id !== documentId));
    } else {
      alert(`문서 삭제 실패: ${res.message}`);
    }
  }

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

  async function assignSegmentSpeaker(segmentId: string, name: string) {
    if (!selectedMeetingId) return;
    const res = await updateMeetingSegmentApi(workspaceId, selectedMeetingId, segmentId, { speakerLabel: name });
    if (res.status === "success" && res.segment) {
      const updated = res.segment;
      setSegments((prev) => prev.map((s) => (s.id === segmentId ? updated : s)));
    } else {
      alert(`화자 이름 지정 실패: ${res.message}`);
    }
  }

  // STT가 잘못 알아들은 발화(예: "9월"을 "구월"로 인식)를 스크립트 탭에서 바로 고칠 수 있게.
  // 성공 여부를 boolean으로 돌려줘서 호출한 쪽(인라인 편집 UI)이 실패 시 편집 모드를 유지하게 한다.
  async function updateSegmentContent(segmentId: string, content: string): Promise<boolean> {
    if (!selectedMeetingId) return false;
    const res = await updateMeetingSegmentApi(workspaceId, selectedMeetingId, segmentId, { content });
    if (res.status === "success" && res.segment) {
      const updated = res.segment;
      setSegments((prev) => prev.map((s) => (s.id === segmentId ? updated : s)));
      return true;
    }
    alert(`회의록 내용 수정 실패: ${res.message}`);
    return false;
  }

  // 한 세그먼트에 서로 다른 화자의 발언이 섞여 있을 때, 특정 지점에서 둘로 나누고 화자를 재지정
  async function splitSegment(segmentId: string, params: SplitSegmentParams): Promise<boolean> {
    if (!selectedMeetingId) return false;
    const res = await splitMeetingSegmentApi(workspaceId, selectedMeetingId, segmentId, params);
    if (res.status === "success" && res.first && res.second) {
      const { first, second } = res;
      setSegments((prev) => [...prev.map((s) => (s.id === segmentId ? first : s)), second]);
      return true;
    }
    alert(`발화 분할 실패: ${res.message}`);
    return false;
  }

  async function updateFullSummary(fullSummary: string) {
    if (!selectedMeetingId) return;
    const res = await updateMeetingSummaryApi(workspaceId, selectedMeetingId, { fullSummary });
    if (res.status === "success" && res.summary) {
      setSummary(res.summary);
    } else {
      alert(`회의록 내용 수정 실패: ${res.message}`);
    }
  }

  async function updateShortSummary(shortSummary: string) {
    if (!selectedMeetingId) return;
    const res = await updateMeetingSummaryApi(workspaceId, selectedMeetingId, { shortSummary });
    if (res.status === "success" && res.summary) {
      setSummary(res.summary);
    } else {
      alert(`요약 수정 실패: ${res.message}`);
    }
  }

  async function addDecision(input: {
    title: string;
    decisionText: string;
    reason?: string;
  }): Promise<boolean> {
    if (!selectedMeetingId) return false;
    const res = await createMeetingDecisionApi(workspaceId, selectedMeetingId, {
      title: input.title,
      decision_text: input.decisionText,
      reason: input.reason,
    });
    if (res.status === "success" && res.decision) {
      setDecisions((prev) => [...prev, res.decision as Decision]);
      return true;
    }
    alert(`결정사항 추가 실패: ${res.message}`);
    return false;
  }

  async function updateDecision(
    decisionId: string,
    input: { title?: string; decisionText?: string; reason?: string | null }
  ): Promise<boolean> {
    if (!selectedMeetingId) return false;
    const res = await updateMeetingDecisionApi(workspaceId, selectedMeetingId, decisionId, {
      title: input.title,
      decision_text: input.decisionText,
      reason: input.reason,
    });
    if (res.status === "success" && res.decision) {
      const updated = res.decision;
      setDecisions((prev) => prev.map((d) => (d.id === decisionId ? updated : d)));
      return true;
    }
    alert(`결정사항 수정 실패: ${res.message}`);
    return false;
  }

  async function approveSuggestedTask(taskId: string): Promise<boolean> {
    const res = await updateTaskStatusApi(workspaceId, taskId, "open");
    if (res.status === "success") {
      setSuggestedTasks((prev) => prev.filter((t) => t.id !== taskId));
      return true;
    }
    alert(`할 일 추가 실패: ${res.message}`);
    return false;
  }

  async function rejectSuggestedTask(taskId: string) {
    const res = await deleteTaskApi(workspaceId, taskId);
    if (res.status === "success") {
      setSuggestedTasks((prev) => prev.filter((t) => t.id !== taskId));
    } else {
      alert(`제안 삭제 실패: ${res.message}`);
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

  async function updateMeetingLocation(location: string): Promise<boolean> {
    if (!selectedMeetingId || !selectedMeeting) return false;
    const res = await updateMeetingInfoApi(workspaceId, selectedMeetingId, {
      title: selectedMeeting.title,
      topic: selectedMeeting.topic,
      location,
    });
    if (res.status === "success" && res.meeting) {
      const updated = res.meeting;
      setMeetings((prev) => prev.map((m) => (m.id === selectedMeetingId ? updated : m)));
      return true;
    }
    alert(`장소 수정 실패: ${res.message}`);
    return false;
  }

  // 회의 종료 직후 서버 목록을 다시 받아오기 전에도 "분석 중" 상태를 바로 보여주기 위한
  // 낙관적 갱신 - reload()가 지연되거나 조용히 실패해도 화면이 빈 상태로 안 보이게 한다.
  function upsertMeeting(meeting: Meeting) {
    setMeetings((prev) =>
      prev.some((m) => m.id === meeting.id)
        ? prev.map((m) => (m.id === meeting.id ? { ...m, ...meeting } : m))
        : [meeting, ...prev]
    );
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
    summaryRefreshedAt,
    decisions,
    addDecision,
    updateDecision,
    attendees,
    documents,
    suggestedTasks,
    approveSuggestedTask,
    rejectSuggestedTask,
    reloadAttendees,
    reloadDocuments,
    removeDocument,
    isDetailLoading,
    isUploading,
    uploadAudio,
    removeMeeting,
    upsertMeeting,
    renameMeeting,
    updateMeetingLocation,
    mapSpeakerNames,
    assignSegmentSpeaker,
    updateSegmentContent,
    splitSegment,
    updateFullSummary,
    updateShortSummary,
    reload: loadMeetings,
  };
}
