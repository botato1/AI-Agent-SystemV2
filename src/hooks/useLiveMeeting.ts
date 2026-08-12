import { useEffect, useRef, useState } from "react";
import {
  Meeting,
  MeetingStart,
  AgendaReminderPopup,
  RecordingMode,
  startMeetingApi,
  joinMeetingApi,
  beginScheduledMeetingApi,
  pauseMeetingApi,
  resumeMeetingApi,
  mapSpeakerNamesApi,
  renameMeetingApi,
  setMeetingAttendeesApi,
  updateMeetingInfoApi,
  updateMeetingSegmentApi,
  getMeetingApi,
  getMeetingListApi,
  getMeetingSegmentsApi,
} from "../services/meeting";

export type LiveMeetingStatus =
  | "idle"
  | "connecting"
  | "recording"
  | "paused"
  | "reconnecting"
  | "ending"
  | "ended"
  | "error";

export interface LiveSegment {
  // STT 오인식(예: "9월"을 "구월"로 인식) 때문에 뜬 모순을 회의 중 바로 고칠 수 있게 하려면
  // 필요하다 - 백엔드가 안 내려주는 예전 응답이면 null이라 그런 회의에선 수정 버튼을 숨긴다.
  id: string | null;
  content: string;
  speaker_label: string | null;
  speaker_user_id: string | null;
  start_ms: number;
  end_ms: number;
}

export type ContradictionAlertSource = "document" | "decision";
// decision_reminder(Case0) - 근거 있는/없는 변경(Case2/3)과 달리 비교·해결 대상이 아니라
// "예전에 이렇게 결정했었다"는 단순 리마인더. 같은 큐에 합쳐서 보여주되 배지로만 구분한다.
export type JudgmentCase = "reasoned_change" | "unreasoned_change" | "decision_reminder";
export type ContradictionAlertAction = "change_acknowledged" | "keep_reference";

export interface ContradictionAlert {
  contradiction_id: string;
  statement_text: string;
  reason: string;
  severity: "low" | "medium" | "high";
  confidence_score: number;
  displayMessage: string | null;
  referenceSourceName: string | null;
  // 근거자료 미리보기용 - 백엔드가 안 내려주는 예전 응답에서는 null이라 뱃지가 안 눌리게 처리
  referenceFileId: string | null;
  // STT 오인식으로 뜬 모순을 "직접 수정하기"로 바로 고칠 수 있게 하는 원본 발화 세그먼트 -
  // 결정 변경 감지(decision_judgment)처럼 세그먼트에 안 걸린 모순은 null
  meetingSegmentId: string | null;
  // decision_judgment(Case2/3, 결정 변경 감지) 전용 필드 - 문서 기반 모순 감지엔 없음
  source: ContradictionAlertSource;
  judgmentCase: JudgmentCase | null;
  actions: ContradictionAlertAction[] | null;
  // decision_reminder(Case0) 전용 필드 - 리마인더가 참조하는 결정 id (해결 대상이 아니라 링크용)
  decisionId: string | null;
}

interface CurrentUserInfo {
  id: string;
  name: string;
}

// STT 서버가 회의 중 오디오 품질 문제(무음, 마이크 미선택/음소거 등)를 감지하면 보내는 경고.
// 같은 경고는 서버가 중복 없이 한 번만 보내므로 프론트에서 따로 dedup할 필요는 없다.
export interface AudioQualityAlert {
  id: string;
  level: string;
  message: string;
  code?: string | null;
}

// 백엔드 STT 서버가 raw PCM16LE / 16kHz / mono만 받기 때문에, MediaRecorder의 기본 압축
// 출력(webm/opus)은 쓸 수 없다. AudioWorklet에서 직접 리샘플링 + PCM 변환해서 스트리밍한다.
const TARGET_SAMPLE_RATE = 16000;
const CHUNK_MS = 200;

// WS가 예기치 않게 끊겼을 때(터널/와이파이 순단 등) 재연결을 시도하는 유예 시간 —
// STT 서버가 이 시간 안에 같은 세션으로 재접속하면 회의를 안 끊고 이어준다.
const RECONNECT_WINDOW_MS = 20000;
const RECONNECT_RETRY_INTERVAL_MS = 1500;

const PCM_WORKLET_SOURCE = `
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.samplesPerChunk = Math.ceil((sampleRate * ${CHUNK_MS}) / 1000);
  }

  process(inputs) {
    const channelData = inputs[0] && inputs[0][0];
    if (channelData && channelData.length > 0) {
      for (let i = 0; i < channelData.length; i++) {
        this.buffer.push(channelData[i]);
      }
    }

    while (this.buffer.length >= this.samplesPerChunk) {
      const block = this.buffer.splice(0, this.samplesPerChunk);
      const pcm16 = this.encode(block);
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }

    return true;
  }

  encode(block) {
    const ratio = sampleRate / ${TARGET_SAMPLE_RATE};
    const outLength = Math.round(block.length / ratio);
    const pcm16 = new Int16Array(outLength);
    for (let i = 0; i < outLength; i++) {
      const srcIndex = Math.min(block.length - 1, Math.floor(i * ratio));
      let sample = Math.max(-1, Math.min(1, block[srcIndex]));
      pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return pcm16;
  }
}

registerProcessor("pcm-processor", PCMProcessor);
`;

function buildWsUrl(apiBaseUrl: string, workspaceId: string, meetingId: string, ticket: string): string {
  const isHttps = apiBaseUrl.startsWith("https");
  const host = apiBaseUrl.replace(/^https?:\/\//, "").replace(/\/$/, "");
  const protocol = isHttps ? "wss" : "ws";
  // voice=1: 각자 PC 모드에서 다른 참가자 목소리를 바이너리 프레임으로 중계받기 위한 옵트인.
  // 한 대의 PC 모드에서는 백엔드가 이 파라미터를 무시한다.
  return `${protocol}://${host}/api/workspaces/${workspaceId}/meetings/${meetingId}/stream?ticket=${encodeURIComponent(
    ticket
  )}&voice=1`;
}

// voice=1로 받는 바이너리 프레임: [1바이트 발신자 슬롯][PCM16LE 16kHz mono 오디오].
// 발신자 슬롯별로 다음 재생 시각을 따로 추적해야 여러 명의 프레임이 한 버퍼에서 뭉개지지 않는다.
function playVoiceFrame(
  ctx: AudioContext | null,
  buffer: ArrayBuffer,
  slotTimelineRef: { current: Map<number, number> }
) {
  if (!ctx || buffer.byteLength < 3) return;

  const view = new DataView(buffer);
  const slot = view.getUint8(0);
  const sampleCount = (buffer.byteLength - 1) / 2;
  if (sampleCount <= 0) return;

  const audioBuffer = ctx.createBuffer(1, sampleCount, TARGET_SAMPLE_RATE);
  const channelData = audioBuffer.getChannelData(0);
  for (let i = 0; i < sampleCount; i++) {
    const sample = view.getInt16(1 + i * 2, true);
    channelData[i] = sample / (sample < 0 ? 0x8000 : 0x7fff);
  }

  const source = ctx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(ctx.destination);

  const timeline = slotTimelineRef.current;
  const now = ctx.currentTime;
  const earliestStart = now + 0.05; // 아주 짧은 버퍼를 둬서 스케줄링 지연으로 인한 끊김을 방지
  const startAt = Math.max(earliestStart, timeline.get(slot) ?? 0);
  source.start(startAt);
  timeline.set(slot, startAt + audioBuffer.duration);
}

// 실시간 회의 녹음 - 마이크 캡처(AudioWorklet) + 웹소켓 오디오 스트리밍 + 실시간 STT 반영
export function useLiveMeeting(workspaceId: string, currentUser: CurrentUserInfo) {
  const [status, setStatus] = useState<LiveMeetingStatus>("idle");
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [segments, setSegments] = useState<LiveSegment[]>([]);
  const [partial, setPartial] = useState<{ confirmed: string; tentative: string }>({
    confirmed: "",
    tentative: "",
  });
  const [contradictionAlerts, setContradictionAlerts] = useState<ContradictionAlert[]>([]);
  const [audioQualityAlerts, setAudioQualityAlerts] = useState<AudioQualityAlert[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [agendaReminder, setAgendaReminder] = useState<AgendaReminderPopup | null>(null);

  // 다른 사람이 이미 시작해둔, 지금 참가할 수 있는 회의가 있는지 - 각자 PC 모드는 참가자로,
  // 한 대의 PC 모드는 보기 전용으로 참가한다 (join()이 recording_mode를 보고 자동으로 구분)
  const [joinableMeeting, setJoinableMeeting] = useState<Meeting | null>(null);

  // 내가 참가자가 아니라 보기 전용(view-only)으로 들어와 있는지 - 오디오 캡처/전송을 건너뛰고,
  // "회의 종료" 대신 "나가기"만 가능하게 UI를 다르게 보여줘야 해서 필요하다.
  const [isViewer, setIsViewer] = useState(false);
  const isViewerRef = useRef(false);

  // 아무것도 안 하고 있을 때만(idle) 참가 가능한 회의가 있는지 주기적으로 확인
  useEffect(() => {
    if (!workspaceId || status !== "idle") {
      setJoinableMeeting(null);
      return;
    }

    let cancelled = false;

    async function poll() {
      const res = await getMeetingListApi(workspaceId);
      if (cancelled) return;
      if (res.status === "success") {
        const found = res.meetings.find((m) => m.status === "recording");
        setJoinableMeeting(found || null);
      }
    }

    poll();
    const timer = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [workspaceId, status]);

  const statusRef = useRef<LiveMeetingStatus>(status);
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const isSendingRef = useRef(false);
  const sessionEndResolverRef = useRef<(() => void) | null>(null);
  // voice=1로 받는 다른 참가자 오디오 프레임 - 발신자 슬롯별 다음 재생 시각
  const voiceSlotTimelineRef = useRef<Map<number, number>>(new Map());

  // 재연결 관련 상태 — 전부 ref로 관리 (WS 이벤트 핸들러는 리렌더 없이도 최신 값을 읽어야 함)
  const isIntentionalCloseRef = useRef(false);
  const reconnectDeadlineRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusBeforeDisconnectRef = useRef<LiveMeetingStatus>("recording");

  function clearReconnectTimer() {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }

  function cleanupAudio() {
    try {
      workletNodeRef.current?.disconnect();
    } catch {
      // no-op
    }
    workletNodeRef.current = null;

    micStreamRef.current?.getTracks().forEach((track) => track.stop());
    micStreamRef.current = null;

    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
  }

  // ws 인스턴스를 직접 클로저로 캡처하지 않고 wsRef.current를 통해 매번 참조한다 —
  // 재연결 시 새 WebSocket으로 wsRef만 교체하면, 마이크 캡처를 다시 세팅하지 않아도
  // (권한 재요청 없이) 이 워클릿이 자동으로 새 소켓에 오디오를 이어 보낸다.
  async function setupAudioCapture() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micStreamRef.current = stream;

    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;

    const workletBlob = new Blob([PCM_WORKLET_SOURCE], { type: "application/javascript" });
    const workletUrl = URL.createObjectURL(workletBlob);
    try {
      await audioContext.audioWorklet.addModule(workletUrl);
    } finally {
      URL.revokeObjectURL(workletUrl);
    }

    const source = audioContext.createMediaStreamSource(stream);
    const workletNode = new AudioWorkletNode(audioContext, "pcm-processor");
    workletNodeRef.current = workletNode;

    workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      const ws = wsRef.current;
      if (isSendingRef.current && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(event.data);
      }
    };

    // 워클릿이 계속 process()를 돌게 하려면 오디오 그래프가 destination까지 연결돼 있어야 하는
    // 브라우저가 있어서, 소리는 안 나가되(gain=0) destination까지 연결해둔다.
    const silentGain = audioContext.createGain();
    silentGain.gain.value = 0;
    source.connect(workletNode);
    workletNode.connect(silentGain);
    silentGain.connect(audioContext.destination);
  }

  // 회의 생성(신규 시작이든, 예약된 회의를 시작하든)이 끝난 뒤 실제로 WS를 붙이고 마이크를
  // 켜는 부분 - start()와 beginScheduled() 둘 다 이 지점부터 완전히 동일하게 동작한다.
  function beginSession(meetingData: MeetingStart) {
    setMeeting(meetingData);
    setAgendaReminder(
      meetingData.agenda_reminder && meetingData.agenda_reminder.items.length > 0
        ? meetingData.agenda_reminder
        : null
    );

    const apiBaseUrl = import.meta.env.VITE_API_URL || window.location.origin;

    function handleMessage(event: MessageEvent<string>) {
      let data: any;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      if (data.type === "partial") {
        setPartial({ confirmed: data.confirmed_text || "", tentative: data.tentative_text || "" });
      } else if (data.type === "final") {
        const newSegments: LiveSegment[] = (data.final?.segments || []).map((s: any) => ({
          id: s.id ?? null,
          content: s.text || "",
          speaker_label: s.speaker ?? null,
          speaker_user_id: s.speaker_user_id ?? null,
          start_ms: Math.round((s.start ?? 0) * 1000),
          end_ms: Math.round((s.end ?? 0) * 1000),
        }));
        if (newSegments.length > 0) {
          setSegments((prev) => [...prev, ...newSegments]);
        }
        setPartial({ confirmed: "", tentative: "" });
      } else if (data.type === "decision_reminder") {
        // Case0(결정 리마인더) - 별도 이벤트 타입. contradiction_id/actions가 없어 해결 대상이 아니고
        // 가벼운 확인용 토스트로만 보여준다. decision_id를 큐 키로 대신 쓴다.
        const alert: ContradictionAlert = {
          contradiction_id: data.decision_id ? `reminder-${data.decision_id}` : `reminder-${crypto.randomUUID()}`,
          statement_text: data.statement_text || "",
          reason: "",
          severity: "low",
          confidence_score: 0,
          displayMessage: data.display_message || null,
          referenceSourceName: null,
          referenceFileId: null,
          meetingSegmentId: null,
          source: "decision",
          judgmentCase: "decision_reminder",
          actions: null,
          decisionId: data.decision_id || null,
        };
        setContradictionAlerts((prev) => [...prev, alert]);
      } else if (data.type === "contradiction_alert") {
        const alert: ContradictionAlert = {
          contradiction_id: data.contradiction_id,
          statement_text: data.statement_text || "",
          reason: data.reason || "",
          severity: data.severity || "low",
          confidence_score: data.confidence_score ?? 0,
          displayMessage: data.display_message || null,
          referenceSourceName: data.reference_source_name || null,
          referenceFileId: data.reference_file_id || null,
          meetingSegmentId: data.meeting_segment_id || null,
          source: data.source === "decision" ? "decision" : "document",
          judgmentCase: data.judgment_case === "reasoned_change" || data.judgment_case === "unreasoned_change"
            ? data.judgment_case
            : null,
          actions: Array.isArray(data.actions) ? data.actions : null,
          // 결정 기반 모순(Case2/3)의 "근거"는 예전 결정 그 자체라, 문서 미리보기처럼
          // 그 결정으로 바로 이동(모달)할 수 있게 id를 같이 받아둔다.
          decisionId: data.reference_decision_id || null,
        };
        setContradictionAlerts((prev) => [...prev, alert]);
      } else if (data.type === "audio_quality") {
        const alert: AudioQualityAlert = {
          id: crypto.randomUUID(),
          level: data.level || "warning",
          message: data.message || "",
          code: data.code ?? null,
        };
        setAudioQualityAlerts((prev) => [...prev, alert]);
      } else if (data.type === "session_end") {
        sessionEndResolverRef.current?.();
        sessionEndResolverRef.current = null;
        // 회의를 직접 끝낸 사람(host)은 stop()이 이미 isIntentionalCloseRef를 true로 켜놓고
        // 이 메시지를 기다리는 중이라, 곧 스스로 소켓을 닫으면서 ws.onclose 경로로 "ended"가
        // 된다. 문제는 그냥 보고만 있던 다른 참가자(뷰어) - 자기가 끝낸 게 아니라서 그 경로를
        // 안 타고, 서버가 뷰어 쪽 소켓은 계속 열어두면 상태가 "recording"에 멈춘 채 새로고침
        // 전까진 회의가 끝난 걸 알 방법이 없었다. 서버가 broadcast하는 session_end 자체를
        // "회의가 끝났다"는 확정 신호로 받아, 뷰어는 여기서 바로 ended로 전환한다.
        if (!isIntentionalCloseRef.current) {
          isSendingRef.current = false;
          cleanupAudio();
          setStatus("ended");
        }
      }
    }

    function giveUpAndEnd() {
      reconnectDeadlineRef.current = null;
      clearReconnectTimer();
      isSendingRef.current = false;
      cleanupAudio();
      wsRef.current = null;
      setStatus("ended");
    }

    // WS가 의도치 않게 끊겼을 때 호출 — 20초 안에서 계속 재시도한다.
    function scheduleReconnect() {
      if (reconnectDeadlineRef.current === null) {
        // 이 재연결 사이클에서 처음 끊긴 순간 — 되돌아갈 상태(recording/paused)와
        // 마감 시각을 여기서 한 번만 기록한다.
        statusBeforeDisconnectRef.current = statusRef.current === "paused" ? "paused" : "recording";
        reconnectDeadlineRef.current = Date.now() + RECONNECT_WINDOW_MS;
      }

      if (Date.now() >= reconnectDeadlineRef.current) {
        giveUpAndEnd();
        return;
      }

      setStatus("reconnecting");
      clearReconnectTimer();
      reconnectTimerRef.current = setTimeout(connect, RECONNECT_RETRY_INTERVAL_MS);
    }

    function connect() {
      const isReconnectAttempt = reconnectDeadlineRef.current !== null;
      const wsUrl = buildWsUrl(apiBaseUrl, workspaceId, meetingData.id, meetingData.ws_ticket);
      const ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";

      ws.onopen = async () => {
        if (isReconnectAttempt) {
          reconnectDeadlineRef.current = null;
          clearReconnectTimer();
          wsRef.current = ws;
          isSendingRef.current = !isViewerRef.current && statusBeforeDisconnectRef.current === "recording";
          setStatus(statusBeforeDisconnectRef.current);
          return;
        }

        wsRef.current = ws;

        // 보기 전용(view-only) 참가는 마이크 권한/캡처가 아예 필요 없다 - 호스트 연결이 받는
        // partial/final을 그대로 구독만 하면 된다.
        if (isViewerRef.current) {
          isSendingRef.current = false;
          setStatus("recording");
          return;
        }

        try {
          await setupAudioCapture();
          isSendingRef.current = true;
          setStatus("recording");
        } catch (err) {
          console.error("마이크 캡처 실패:", err);
          setErrorMessage("마이크 접근에 실패했습니다. 브라우저 권한을 확인해 주세요.");
          setStatus("error");
          isIntentionalCloseRef.current = true;
          ws.close();
        }
      };

      ws.onmessage = (event: MessageEvent<string | ArrayBuffer>) => {
        if (event.data instanceof ArrayBuffer) {
          playVoiceFrame(audioContextRef.current, event.data, voiceSlotTimelineRef);
          return;
        }
        handleMessage(event as MessageEvent<string>);
      };

      ws.onerror = () => {
        if (!isReconnectAttempt) {
          setErrorMessage("실시간 녹음 연결에 문제가 발생했습니다.");
        }
      };

      ws.onclose = () => {
        if (isIntentionalCloseRef.current) {
          isSendingRef.current = false;
          cleanupAudio();
          wsRef.current = null;
          setStatus((prev) => (prev === "error" ? "error" : "ended"));
          return;
        }
        // 의도치 않은 종료(네트워크 순단 등) — 재연결 시도
        isSendingRef.current = false;
        scheduleReconnect();
      };
    }

    connect();
  }

  function resetSessionState() {
    setErrorMessage(null);
    setStatus("connecting");
    setSegments([]);
    setPartial({ confirmed: "", tentative: "" });
    setContradictionAlerts([]);
    setAudioQualityAlerts([]);
    setAgendaReminder(null);
    isIntentionalCloseRef.current = false;
    reconnectDeadlineRef.current = null;
    clearReconnectTimer();
    voiceSlotTimelineRef.current.clear();
    isViewerRef.current = false;
    setIsViewer(false);
  }

  function clearAgendaReminder() {
    setAgendaReminder(null);
  }

  async function start(
    title: string,
    relatedRoomId?: string,
    attendeeIds?: string[],
    location?: string,
    recordingMode?: RecordingMode
  ) {
    if (status === "recording" || status === "connecting") return;
    resetSessionState();

    const res = await startMeetingApi(workspaceId, title, relatedRoomId, recordingMode);
    if (res.status !== "success" || !res.meeting) {
      setStatus("error");
      setErrorMessage(res.message);
      return;
    }

    // 시작 전 미리 고른 참석자가 있으면 회의 생성 직후 바로 지정 - 녹음 자체를
    // 막을 필요는 없으니 결과를 기다리지 않는다 (실패해도 회의 상세에서 나중에 다시 지정 가능)
    if (attendeeIds && attendeeIds.length > 0) {
      setMeetingAttendeesApi(workspaceId, res.meeting.id, attendeeIds);
    }

    // 장소도 마찬가지 - start API엔 없는 필드라, 생성 직후 기존 "회의 정보 수정" API로 반영한다
    if (location) {
      updateMeetingInfoApi(workspaceId, res.meeting.id, { title, location });
    }

    beginSession(res.meeting);
  }

  // 다른 사람이 시작해둔 회의에 내 몫의 티켓을 받아서 합류한다. 각자 PC 모드면 나도 참가자로
  // 마이크를 캡처하고, 한 대의 PC 모드면 서버가 보기 전용 티켓을 내려주므로 오디오 없이 구독만 한다.
  async function join(meetingId: string) {
    if (status === "recording" || status === "connecting") return;
    resetSessionState();

    // 이미 진행 중인 회의에 나중에 들어오는 경우, 그 전까지 오간 발화는 앞으로 올 WS
    // "final" 이벤트에 안 실려서 새로고침 전까진 화면이 비어 보였다 - 참가 시점에
    // 지금까지의 스크립트를 REST로 한 번 채워두고, 이후는 그대로 WS로 이어붙인다.
    const [meetingRes, joinRes, segmentsRes] = await Promise.all([
      getMeetingApi(workspaceId, meetingId),
      joinMeetingApi(workspaceId, meetingId),
      getMeetingSegmentsApi(workspaceId, meetingId),
    ]);

    if (meetingRes.status !== "success" || !meetingRes.meeting || joinRes.status !== "success" || !joinRes.wsTicket) {
      setStatus("error");
      setErrorMessage(joinRes.message || meetingRes.message);
      return;
    }

    const viewOnly = meetingRes.meeting.recording_mode !== "individual";
    isViewerRef.current = viewOnly;
    setIsViewer(viewOnly);

    beginSession({ ...meetingRes.meeting, ws_ticket: joinRes.wsTicket });

    if (segmentsRes.status === "success" && segmentsRes.segments.length > 0) {
      setSegments(
        [...segmentsRes.segments]
          .sort((a, b) => a.segment_index - b.segment_index)
          .map((s) => ({
            id: s.id,
            content: s.content,
            speaker_label: s.speaker_label ?? null,
            speaker_user_id: s.speaker_user_id ?? null,
            start_ms: s.start_ms,
            end_ms: s.end_ms,
          }))
      );
    }
  }

  // 예약해둔 회의를 실제 녹음으로 전환한다 - 참석자는 예약 시점에 이미 지정돼 있으므로 다시 넘길 필요 없음
  async function beginScheduled(meetingId: string) {
    if (status === "recording" || status === "connecting") return;
    resetSessionState();

    const res = await beginScheduledMeetingApi(workspaceId, meetingId);
    if (res.status !== "success" || !res.meeting) {
      setStatus("error");
      setErrorMessage(res.message);
      return;
    }

    beginSession(res.meeting);
  }

  async function pause() {
    if (status !== "recording" || !meeting) return;
    const res = await pauseMeetingApi(workspaceId, meeting.id);
    if (res.status === "success") {
      isSendingRef.current = false;
      setStatus("paused");
    } else {
      alert(`일시정지 실패: ${res.message}`);
    }
  }

  async function resume() {
    if (status !== "paused" || !meeting) return;
    const res = await resumeMeetingApi(workspaceId, meeting.id);
    if (res.status === "success") {
      isSendingRef.current = true;
      setStatus("recording");
    } else {
      alert(`재개 실패: ${res.message}`);
    }
  }

  function clearContradictionAlert(contradictionId: string) {
    setContradictionAlerts((prev) => prev.filter((a) => a.contradiction_id !== contradictionId));
  }

  function clearAudioQualityAlert(alertId: string) {
    setAudioQualityAlerts((prev) => prev.filter((a) => a.id !== alertId));
  }

  async function mapSpeakerNames(mapping: Record<string, string>) {
    if (!meeting) return;
    const res = await mapSpeakerNamesApi(workspaceId, meeting.id, mapping);
    if (res.status === "success") {
      // 이미 표시된 발화도 즉시 소급 반영 (앞으로 들어오는 발화는 백엔드가 이미 매핑해서 보내줌)
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

  // STT 오인식(예: "9월"을 "구월"로 인식)으로 뜬 모순을 회의 중 바로 고칠 수 있게 - 세그먼트
  // 내용을 수정하고, 성공하면 스크립트에도 바로 반영한다. 실패 시 false를 돌려줘서 호출한
  // 쪽(모순 카드)이 무시 처리로 안 넘어가고 에러만 보여주게 한다.
  async function editSegmentContent(segmentId: string, content: string): Promise<boolean> {
    if (!meeting) return false;
    const res = await updateMeetingSegmentApi(workspaceId, meeting.id, segmentId, { content });
    if (res.status === "success") {
      setSegments((prev) => prev.map((s) => (s.id === segmentId ? { ...s, content } : s)));
      return true;
    }
    alert(`발화 내용 수정 실패: ${res.message}`);
    return false;
  }

  async function renameMeeting(title: string) {
    if (!meeting) return;
    const res = await renameMeetingApi(workspaceId, meeting.id, title);
    if (res.status === "success" && res.meeting) {
      setMeeting(res.meeting);
    } else {
      alert(`회의 제목 변경 실패: ${res.message}`);
    }
  }

  async function stop() {
    const ws = wsRef.current;
    if (!ws || (status !== "recording" && status !== "paused")) return;

    setStatus("ending");
    isSendingRef.current = false;
    isIntentionalCloseRef.current = true;
    reconnectDeadlineRef.current = null;
    clearReconnectTimer();

    // session_end는 밀려 있는 자막이 많으면 최대 1분까지 걸릴 수 있다 - 그보다 짧게 잡으면
    // 서버가 마지막 자막을 다 보내기 전에 소켓을 닫아버려서 회의 후반부 스크립트가 화면에서
    // 잘려 보인다 (회의록엔 남지만 회의 중 화면에는 안 뜬 채로 끝나버림).
    const SESSION_END_TIMEOUT_MS = 60000;
    const waitForSessionEnd = new Promise<void>((resolve) => {
      sessionEndResolverRef.current = resolve;
      setTimeout(resolve, SESSION_END_TIMEOUT_MS);
    });

    if (ws.readyState === WebSocket.OPEN) {
      ws.send("end");
    }
    await waitForSessionEnd;
    ws.close();
  }

  // 보기 전용 참가자가 회의에서 빠지는 것 - stop()과 달리 "end"를 보내지 않는다(회의 자체를
  // 끝내는 게 아니라 내 구독 연결만 닫는 거라, 호스트나 다른 참가자에게는 영향이 없어야 한다).
  function leave() {
    isIntentionalCloseRef.current = true;
    reconnectDeadlineRef.current = null;
    clearReconnectTimer();
    isSendingRef.current = false;
    wsRef.current?.close();
    wsRef.current = null;
    cleanupAudio();
    reset();
  }

  function reset() {
    setStatus("idle");
    setMeeting(null);
    setSegments([]);
    setPartial({ confirmed: "", tentative: "" });
    setContradictionAlerts([]);
    setAudioQualityAlerts([]);
    setAgendaReminder(null);
    setErrorMessage(null);
    isIntentionalCloseRef.current = false;
    reconnectDeadlineRef.current = null;
    clearReconnectTimer();
    voiceSlotTimelineRef.current.clear();
    isViewerRef.current = false;
    setIsViewer(false);
  }

  useEffect(() => {
    return () => {
      isIntentionalCloseRef.current = true;
      clearReconnectTimer();
      wsRef.current?.close();
      cleanupAudio();
    };
  }, []);

  return {
    status,
    meeting,
    segments,
    partial,
    contradictionAlerts,
    audioQualityAlerts,
    agendaReminder,
    clearAgendaReminder,
    errorMessage,
    joinableMeeting,
    isViewer,
    start,
    join,
    beginScheduled,
    pause,
    resume,
    stop,
    leave,
    reset,
    mapSpeakerNames,
    editSegmentContent,
    clearContradictionAlert,
    clearAudioQualityAlert,
    renameMeeting,
    startedByName: currentUser.name,
  };
}
