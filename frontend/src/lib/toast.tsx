import { useEffect, useState } from "react";
import { WarningIcon, CloseIcon } from "../components/icons";

interface ToastItem {
  id: number;
  message: string;
}

type Listener = (toasts: ToastItem[]) => void;

let toasts: ToastItem[] = [];
let nextId = 0;
const listeners = new Set<Listener>();

function emit() {
  listeners.forEach((listener) => listener(toasts));
}

const TOAST_DURATION_MS = 4000;

// alert() 네이티브 팝업 대신 앱 톤에 맞춰 에러 메시지를 보여주는 토스트. 훅(hook)에서도 props
// 없이 바로 부를 수 있도록 컴포넌트 트리와 무관한 모듈 전역 상태로 관리한다 - <ToastContainer />를
// 트리 어딘가(App.tsx)에 한 번만 마운트해두면, 그 아래 어디서든 이 함수만 import해서 쓰면 된다.
export function showToast(message: string) {
  const id = nextId++;
  toasts = [...toasts, { id, message }];
  emit();
  setTimeout(() => {
    toasts = toasts.filter((toast) => toast.id !== id);
    emit();
  }, TOAST_DURATION_MS);
}

function dismissToast(id: number) {
  toasts = toasts.filter((toast) => toast.id !== id);
  emit();
}

export function ToastContainer() {
  const [items, setItems] = useState<ToastItem[]>(toasts);

  useEffect(() => {
    listeners.add(setItems);
    return () => {
      listeners.delete(setItems);
    };
  }, []);

  if (items.length === 0) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-[100] flex flex-col items-center gap-2 px-4">
      {items.map((item) => (
        <div
          key={item.id}
          className="pointer-events-auto flex w-full max-w-md items-start gap-2 rounded-xl border border-recall-danger/30 bg-recall-bg px-4 py-3 text-sm text-recall-text shadow-2xl"
        >
          <WarningIcon size={16} className="mt-0.5 flex-shrink-0 text-recall-danger" />
          <p className="flex-1 leading-relaxed">{item.message}</p>
          <button
            onClick={() => dismissToast(item.id)}
            className="flex-shrink-0 text-recall-textMuted hover:text-recall-text"
          >
            <CloseIcon size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
