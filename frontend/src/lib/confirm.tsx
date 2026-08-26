import { useEffect, useState } from "react";

interface ConfirmRequest {
  id: number;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  resolve: (value: boolean) => void;
}

type Listener = (request: ConfirmRequest | null) => void;

let current: ConfirmRequest | null = null;
let nextId = 0;
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((listener) => listener(current));
}

// window.confirm 네이티브 팝업 대신 앱 톤에 맞춘 확인 모달. 컴포넌트 트리 어디서든(훅 포함)
// await로 바로 호출할 수 있도록 모듈 전역 상태 + Promise로 구현했다 - <ConfirmDialogContainer />를
// 트리 어딘가(App.tsx)에 한 번만 마운트해두면 된다. 동시에 하나만 띄운다 - 이미 뜬 확인창이
// 있으면 그건 취소로 처리하고 새 요청으로 교체한다.
export function showConfirm(message: string, confirmLabel: string, cancelLabel: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (current) current.resolve(false);
    current = { id: nextId++, message, confirmLabel, cancelLabel, resolve };
    emit();
  });
}

function settle(value: boolean) {
  if (!current) return;
  current.resolve(value);
  current = null;
  emit();
}

export function ConfirmDialogContainer() {
  const [request, setRequest] = useState<ConfirmRequest | null>(current);

  useEffect(() => {
    listeners.add(setRequest);
    return () => {
      listeners.delete(setRequest);
    };
  }, []);

  if (!request) return null;

  return (
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-black/50 p-4"
      onClick={() => settle(false)}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bg p-5 shadow-2xl text-recall-text"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="mb-4 whitespace-pre-wrap text-sm leading-relaxed">{request.message}</p>
        <div className="flex gap-2">
          <button
            onClick={() => settle(false)}
            className="flex-1 rounded-lg border border-recall-border px-3 py-2 text-xs text-recall-textMuted hover:bg-white/5"
          >
            {request.cancelLabel}
          </button>
          <button
            onClick={() => settle(true)}
            className="flex-1 rounded-lg bg-recall-accent px-3 py-2 text-xs font-medium text-white hover:opacity-90"
          >
            {request.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
