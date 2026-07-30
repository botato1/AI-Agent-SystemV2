import { useEffect, useRef, useState } from "react";

interface AvatarCropModalProps {
  file: File;
  onCancel: () => void;
  onConfirm: (croppedFile: File) => void;
}

const CONTAINER_SIZE = 260;
const OUTPUT_SIZE = 400;

export default function AvatarCropModal({ file, onCancel, onConfirm }: AvatarCropModalProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  const imgRef = useRef<HTMLImageElement>(null);
  const draggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0, offsetX: 0, offsetY: 0 });

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const baseScale = naturalSize ? CONTAINER_SIZE / Math.min(naturalSize.w, naturalSize.h) : 1;
  const effectiveScale = baseScale * zoom;
  const displayWidth = naturalSize ? naturalSize.w * effectiveScale : 0;
  const displayHeight = naturalSize ? naturalSize.h * effectiveScale : 0;

  function clampOffset(x: number, y: number) {
    const excessX = Math.max(0, (displayWidth - CONTAINER_SIZE) / 2);
    const excessY = Math.max(0, (displayHeight - CONTAINER_SIZE) / 2);
    return {
      x: Math.min(excessX, Math.max(-excessX, x)),
      y: Math.min(excessY, Math.max(-excessY, y)),
    };
  }

  function handleImageLoad() {
    const img = imgRef.current;
    if (!img) return;
    setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
    setOffset({ x: 0, y: 0 });
  }

  function handlePointerDown(e: React.PointerEvent) {
    draggingRef.current = true;
    dragStartRef.current = { x: e.clientX, y: e.clientY, offsetX: offset.x, offsetY: offset.y };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }

  function handlePointerMove(e: React.PointerEvent) {
    if (!draggingRef.current) return;
    const dx = e.clientX - dragStartRef.current.x;
    const dy = e.clientY - dragStartRef.current.y;
    setOffset(clampOffset(dragStartRef.current.offsetX + dx, dragStartRef.current.offsetY + dy));
  }

  function handlePointerUp() {
    draggingRef.current = false;
  }

  function handleZoomChange(newZoom: number) {
    setZoom(newZoom);
    setOffset((prev) => clampOffset(prev.x, prev.y));
  }

  function handleWheel(e: React.WheelEvent) {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
    handleZoomChange(Math.min(3, Math.max(1, zoom * factor)));
  }

  function handleConfirm() {
    const img = imgRef.current;
    if (!img || !naturalSize) return;

    const ratio = OUTPUT_SIZE / CONTAINER_SIZE;
    const drawWidth = displayWidth * ratio;
    const drawHeight = displayHeight * ratio;
    const drawX = OUTPUT_SIZE / 2 + offset.x * ratio - drawWidth / 2;
    const drawY = OUTPUT_SIZE / 2 + offset.y * ratio - drawHeight / 2;

    const canvas = document.createElement("canvas");
    canvas.width = OUTPUT_SIZE;
    canvas.height = OUTPUT_SIZE;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(img, drawX, drawY, drawWidth, drawHeight);

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        onConfirm(new File([blob], "avatar.jpg", { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92
    );
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-sm rounded-2xl border border-recall-border bg-recall-bgSoft p-6 shadow-xl text-recall-text">
        <h2 className="mb-4 text-lg font-bold">사진 위치 조정</h2>

        <div
          className="relative mx-auto overflow-hidden rounded-full bg-black/20 touch-none select-none"
          style={{ width: CONTAINER_SIZE, height: CONTAINER_SIZE, cursor: draggingRef.current ? "grabbing" : "grab" }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
          onWheel={handleWheel}
        >
          {imageUrl && (
            <img
              ref={imgRef}
              src={imageUrl}
              onLoad={handleImageLoad}
              alt="크롭할 이미지"
              draggable={false}
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                width: displayWidth || undefined,
                height: displayHeight || undefined,
                transform: `translate(-50%, -50%) translate(${offset.x}px, ${offset.y}px)`,
              }}
            />
          )}
        </div>

        <p className="mt-3 text-center text-xs text-recall-textMuted">
          드래그해서 위치 이동 · 마우스 휠로 확대/축소
        </p>

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-recall-border px-4 py-2 text-sm text-recall-textMuted hover:bg-white/5"
          >
            취소
          </button>
          <button
            onClick={handleConfirm}
            disabled={!naturalSize}
            className="rounded-lg bg-recall-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 transition"
          >
            적용
          </button>
        </div>
      </div>
    </div>
  );
}
