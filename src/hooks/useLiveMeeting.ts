import { useEffect, useRef, useState } from "react";
import { Meeting, startMeetingApi, pauseMeetingApi, resumeMeetingApi } from "../services/meeting";

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
  content: string;
  speaker_label: string | null;
  start_ms: number;
  end_ms: number;
}

export interface ContradictionAlert {
  contradiction_id: string;
  statement_text: string;
  reason: string;
  severity: "low" | "medium" | "high";
  confidence_score: number;
}

interface CurrentUserInfo {
  id: string;
  name: string;
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
  return `${protocol}://${host}/api/workspaces/${workspaceId}/meetings/${meetingId}/stream?ticket=${encodeURIComponent(
    ticket
  )}`;
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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

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

  async function start(title: string, relatedRoomId?: string) {
    if (status === "recording" || status === "connecting") return;

    setErrorMessage(null);
    setStatus("connecting");
    setSegments([]);
    setPartial({ confirmed: "", tentative: "" });
    setContradictionAlerts([]);
    isIntentionalCloseRef.current = false;
    reconnectDeadlineRef.current = null;
    clearReconnectTimer();

    const res = await startMeetingApi(workspaceId, title, relatedRoomId);
    if (res.status !== "success" || !res.meeting) {
      setStatus("error");
      setErrorMessage(res.message);
      return;
    }

    // 재연결 시에도 그대로 재사용할 값 — React state(meeting)는 비동기라 클로저에서
    // 참조하면 오래된 값을 읽을 위험이 있어, 여기 지역 변수로 직접 들고 있는다.
    const meetingData = res.meeting;
    setMeeting(meetingData);

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
          content: s.text || "",
          speaker_label: s.speaker ?? null,
          start_ms: Math.round((s.start ?? 0) * 1000),
          end_ms: Math.round((s.end ?? 0) * 1000),
        }));
        if (newSegments.length > 0) {
          setSegments((prev) => [...prev, ...newSegments]);
        }
        setPartial({ confirmed: "", tentative: "" });
      } else if (data.type === "contradiction_alert") {
        const alert: ContradictionAlert = {
          contradiction_id: data.contradiction_id,
          statement_text: data.statement_text || "",
          reason: data.reason || "",
          severity: data.severity || "low",
          confidence_score: data.confidence_score ?? 0,
        };
        setContradictionAlerts((prev) => [...prev, alert]);
      } else if (data.type === "session_end") {
        sessionEndResolverRef.current?.();
        sessionEndResolverRef.current = null;
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

      ws.onopen = async () => {
        if (isReconnectAttempt) {
          reconnectDeadlineRef.current = null;
          clearReconnectTimer();
          wsRef.current = ws;
          isSendingRef.current = statusBeforeDisconnectRef.current === "recording";
          setStatus(statusBeforeDisconnectRef.current);
          return;
        }

        wsRef.current = ws;
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

      ws.onmessage = handleMessage;

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

  async function stop() {
    const ws = wsRef.current;
    if (!ws || (status !== "recording" && status !== "paused")) return;

    setStatus("ending");
    isSendingRef.current = false;
    isIntentionalCloseRef.current = true;
    reconnectDeadlineRef.current = null;
    clearReconnectTimer();

    const waitForSessionEnd = new Promise<void>((resolve) => {
      sessionEndResolverRef.current = resolve;
      setTimeout(resolve, 5000);
    });

    if (ws.readyState === WebSocket.OPEN) {
      ws.send("end");
    }
    await waitForSessionEnd;
    ws.close();
  }

  function reset() {
    setStatus("idle");
    setMeeting(null);
    setSegments([]);
    setPartial({ confirmed: "", tentative: "" });
    setContradictionAlerts([]);
    setErrorMessage(null);
    isIntentionalCloseRef.current = false;
    reconnectDeadlineRef.current = null;
    clearReconnectTimer();
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
    errorMessage,
    start,
    pause,
    resume,
    stop,
    reset,
    startedByName: currentUser.name,
  };
}
