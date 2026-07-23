import { useEffect, useRef, useState } from "react";
import { Meeting, startMeetingApi, pauseMeetingApi, resumeMeetingApi } from "../services/meeting";

export type LiveMeetingStatus =
  | "idle"
  | "connecting"
  | "recording"
  | "paused"
  | "ending"
  | "ended"
  | "error";

export interface LiveSegment {
  content: string;
  speaker_label: string | null;
  start_ms: number;
  end_ms: number;
}

interface CurrentUserInfo {
  id: string;
  name: string;
}

// 백엔드 STT 서버가 raw PCM16LE / 16kHz / mono만 받기 때문에, MediaRecorder의 기본 압축
// 출력(webm/opus)은 쓸 수 없다. AudioWorklet에서 직접 리샘플링 + PCM 변환해서 스트리밍한다.
const TARGET_SAMPLE_RATE = 16000;
const CHUNK_MS = 200;

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
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const isSendingRef = useRef(false);
  const sessionEndResolverRef = useRef<(() => void) | null>(null);

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

  async function setupAudioCapture(ws: WebSocket) {
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
      if (isSendingRef.current && ws.readyState === WebSocket.OPEN) {
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

    const res = await startMeetingApi(workspaceId, title, relatedRoomId);
    if (res.status !== "success" || !res.meeting) {
      setStatus("error");
      setErrorMessage(res.message);
      return;
    }

    setMeeting(res.meeting);

    const apiBaseUrl = import.meta.env.VITE_API_URL || window.location.origin;
    const wsUrl = buildWsUrl(apiBaseUrl, workspaceId, res.meeting.id, res.meeting.ws_ticket);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = async () => {
      try {
        await setupAudioCapture(ws);
        isSendingRef.current = true;
        setStatus("recording");
      } catch (err) {
        console.error("마이크 캡처 실패:", err);
        setErrorMessage("마이크 접근에 실패했습니다. 브라우저 권한을 확인해 주세요.");
        setStatus("error");
        ws.close();
      }
    };

    ws.onmessage = (event: MessageEvent<string>) => {
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
      } else if (data.type === "session_end") {
        sessionEndResolverRef.current?.();
        sessionEndResolverRef.current = null;
      }
    };

    ws.onerror = () => {
      setErrorMessage("실시간 녹음 연결에 문제가 발생했습니다.");
    };

    ws.onclose = () => {
      isSendingRef.current = false;
      cleanupAudio();
      wsRef.current = null;
      setStatus((prev) => (prev === "error" ? "error" : "ended"));
    };
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
    setErrorMessage(null);
  }

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      cleanupAudio();
    };
  }, []);

  return {
    status,
    meeting,
    segments,
    partial,
    errorMessage,
    start,
    pause,
    resume,
    stop,
    reset,
    startedByName: currentUser.name,
  };
}
