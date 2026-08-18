import React, { useState, useEffect, useRef } from "react";
import {
  getVoiceScriptApi,
  registerVoiceProfileApi,
  VoiceProfileStatus,
} from "../services/voice";

interface VoiceRegisterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (status: VoiceProfileStatus) => void;
}

export function VoiceRegisterModal({
  isOpen,
  onClose,
  onSuccess,
}: VoiceRegisterModalProps) {
  const [script, setScript] = useState<string>("문장을 불러오는 중...");
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // 등록 완료 상태 모드 (alert 대신 모달 내에서 이쁘게 보여주기 위함)
  const [completedStatus, setCompletedStatus] = useState<VoiceProfileStatus | null>(null);

  // 이름 인식 실패 시 수동 입력 폴백용 State
  const [fallbackMode, setFallbackMode] = useState<boolean>(false);
  const [customName, setCustomName] = useState<string>("");
  const [pcmBufferCache, setPcmBufferCache] = useState<ArrayBuffer | null>(null);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const pcmChunksRef = useRef<Float32Array[]>([]);

  useEffect(() => {
    if (isOpen) {
      resetState();
      fetchScript();
    } else {
      stopRecording();
    }
  }, [isOpen]);

  const resetState = () => {
    setIsRecording(false);
    setIsSubmitting(false);
    setErrorMessage(null);
    setFallbackMode(false);
    setCompletedStatus(null);
    setCustomName("");
    setPcmBufferCache(null);
    pcmChunksRef.current = [];
  };

  const fetchScript = async () => {
    const res = await getVoiceScriptApi();
    if (res.status === "success" && res.script) {
      setScript(res.script);
    } else {
      setErrorMessage(res.message);
    }
  };

  const startRecording = async () => {
    setErrorMessage(null);
    pcmChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const audioCtx = new (window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)({
        sampleRate: 16000,
      });
      audioCtxRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        pcmChunksRef.current.push(new Float32Array(inputData));
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      setIsRecording(true);
    } catch (err) {
      console.error("마이크 접근 실패:", err);
      setErrorMessage("마이크 접근 권한이 필요합니다.");
    }
  };

  const stopRecordingAndSend = async () => {
    if (!isRecording) return;

    setIsRecording(false);
    setIsSubmitting(true);

    if (processorRef.current) processorRef.current.disconnect();
    if (streamRef.current) streamRef.current.getTracks().forEach((track) => track.stop());
    if (audioCtxRef.current) await audioCtxRef.current.close();

    const totalSamples = pcmChunksRef.current.reduce((acc, curr) => acc + curr.length, 0);
    const mergedSamples = new Float32Array(totalSamples);
    let offset = 0;
    for (const chunk of pcmChunksRef.current) {
      mergedSamples.set(chunk, offset);
      offset += chunk.length;
    }

    const pcm16Buffer = new ArrayBuffer(mergedSamples.length * 2);
    const view = new DataView(pcm16Buffer);
    for (let i = 0; i < mergedSamples.length; i++) {
      const s = Math.max(-1, Math.min(1, mergedSamples[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }

    setPcmBufferCache(pcm16Buffer);
    await handleRegister(pcm16Buffer);
  };

  const handleRegister = async (pcmBuffer: ArrayBuffer, speakerName?: string) => {
    setIsSubmitting(true);
    setErrorMessage(null);

    const res = await registerVoiceProfileApi(pcmBuffer, speakerName);

    setIsSubmitting(false);

    if (res.status === "error") {
      setErrorMessage(res.message);
      return;
    }

    if (res.data) {
      if (res.data.name_extraction_failed && !speakerName) {
        setFallbackMode(true);
      } else if (res.data.registered) {
        // alert() 삭제 -> 모달 내부 완료 카드 상태로 변경
        setCompletedStatus(res.data);
      }
    }
  };

  const handleFallbackSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customName.trim()) {
      setErrorMessage("이름을 입력해 주세요.");
      return;
    }
    if (pcmBufferCache) {
      handleRegister(pcmBufferCache, customName.trim());
    }
  };

  const handleFinish = () => {
    if (completedStatus && onSuccess) {
      onSuccess(completedStatus);
    }
    onClose();
  };

  const stopRecording = () => {
    if (processorRef.current) processorRef.current.disconnect();
    if (streamRef.current) streamRef.current.getTracks().forEach((track) => track.stop());
    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-xl text-recall-text transition-all">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold">목소리 등록</h2>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="text-recall-textMuted hover:text-recall-text text-sm"
          >
            ✕
          </button>
        </div>

        {/* 1. 등록 완료 화면 (alert 대신 보일 이쁜 완료 UI) */}
        {completedStatus ? (
          <div className="flex flex-col items-center justify-center my-6 gap-3 text-center">
            <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold text-xl">
              ✓
            </div>
            <div>
              <p className="text-base font-semibold text-recall-text">
                목소리가 정상적으로 등록되었습니다
              </p>
              <p className="text-xs text-recall-textMuted mt-1">
                인식된 이름: <span className="text-emerald-400 font-medium">{completedStatus.speaker_name}</span>
              </p>
            </div>
            <button
              onClick={handleFinish}
              className="mt-3 w-full max-w-[280px] rounded-full bg-recall-accent py-2.5 text-sm font-medium text-white hover:opacity-90 transition shadow-sm"
            >
              확인
            </button>
          </div>
        ) : (
          /* 2. 기존 녹음 진행 화면 */
          <>
            <p className="text-xs text-recall-textMuted mb-4 leading-relaxed">
              아래의 문장을 가볍게 끝까지 읽어주세요. (약 10~12초 권장)
            </p>

            <div className="rounded-xl border border-recall-border/60 bg-white/5 p-4 text-sm leading-relaxed text-recall-text mb-4">
              <p>{script}</p>
            </div>

            {errorMessage && (
              <p className="text-xs text-recall-danger mb-3 leading-relaxed">{errorMessage}</p>
            )}

            {fallbackMode ? (
              <form onSubmit={handleFallbackSubmit} className="flex flex-col gap-2.5 my-2">
                <p className="text-xs text-amber-400 font-medium leading-relaxed">
                  음성에서 이름을 자동으로 인식하지 못했습니다. 성함을 직접 입력해 주세요.
                </p>
                <input
                  type="text"
                  placeholder="이름 입력 (예: 홍길동)"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  className="w-full rounded-lg border border-recall-border bg-transparent px-3 py-2 text-sm focus:outline-none focus:border-recall-accent"
                />
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full rounded-full bg-recall-accent py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 transition"
                >
                  {isSubmitting ? "등록 중..." : "이름으로 등록 완료"}
                </button>
              </form>
            ) : (
              <div className="flex flex-col items-center justify-center my-4 gap-2">
                {!isRecording ? (
                  <button
                    onClick={startRecording}
                    disabled={isSubmitting}
                    className="w-full max-w-[280px] rounded-full bg-red-600 py-3 px-6 text-sm font-semibold text-white hover:bg-red-500 active:scale-95 disabled:opacity-50 transition-all shadow-md"
                  >
                    녹음 시작
                  </button>
                ) : (
                  <button
                    onClick={stopRecordingAndSend}
                    className="w-full max-w-[280px] rounded-full bg-red-700 py-3 px-6 text-sm font-semibold text-white hover:bg-red-800 active:scale-95 transition-all shadow-md animate-pulse"
                  >
                    녹음 완료 및 등록
                  </button>
                )}

                {isSubmitting && (
                  <p className="text-xs text-recall-textMuted mt-2">음성을 분석하여 등록 중입니다...</p>
                )}
              </div>
            )}

            <div className="flex justify-end mt-4 pt-2 border-t border-recall-border/40">
              <button
                onClick={onClose}
                disabled={isSubmitting}
                className="rounded-lg border border-recall-border px-4 py-1.5 text-xs text-recall-textMuted hover:bg-white/5 transition"
              >
                취소
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default VoiceRegisterModal;