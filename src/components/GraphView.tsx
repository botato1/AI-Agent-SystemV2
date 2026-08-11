import { useEffect, useRef, useState } from "react";
import { AnalyzedDocument } from "../types";
import { getDocumentGraphApi } from "../services/document";

import DocumentPreviewModal from "./DocumentPreviewModal";
import { CloseIcon, MenuIcon, PlusIcon, MinusIcon, RepeatIcon, SearchIcon } from "./icons";

interface GraphViewProps {
  workspaceId: string;
  documents: AnalyzedDocument[];
  t: any;
}

// 파일 확장자별 카테고리 색상 — 진짜 문서 유형/토픽 분류가 생기기 전까지 확장자를 임시 카테고리로 사용
const EXT_GROUP: Record<string, number> = { PDF: 1, DOCX: 2, HWPX: 3, PNG: 4, JPG: 4, JPEG: 4, TXT: 5 };
const GROUP_COLORS = ["#7c6af7", "#4caf82", "#e8a838", "#ec7fb0", "#5bb8d9", "#94a3b8"]; // 마지막은 "기타"
const GROUP_LABELS: Record<number, string> = {
  1: "PDF",
  2: "DOCX",
  3: "HWPX",
  4: "이미지",
  5: "TXT",
  6: "기타",
};

function getExtGroup(filename: string): number {
  const ext = filename.split(".").pop()?.toUpperCase() ?? "";
  return EXT_GROUP[ext] ?? 6;
}

function getGroupColor(group: number): string {
  return GROUP_COLORS[(group - 1) % GROUP_COLORS.length];
}

// 노드 아래 상시 라벨 - 그래프가 복잡해질 때 라벨끼리 너무 뒤엉키지 않도록 글자 수를 제한한다
const MAX_LABEL_CHARS = 16;
function truncateLabel(name: string): string {
  if (name.length <= MAX_LABEL_CHARS) return name;
  return `${name.slice(0, MAX_LABEL_CHARS - 1)}…`;
}

interface Node {
  id: string;
  name: string;
  group: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
}

interface Edge {
  a: string;
  b: string;
  strength: number; // 0~1
}

export default function GraphView({ workspaceId, documents, t }: GraphViewProps) {
  const analyzedDocs = documents.filter((d) => d.status === "analyzed");
  const analyzedIds = analyzedDocs.map((d) => d.id).join(",");

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const nodesRef = useRef<Node[]>([]);
  const edgesRef = useRef<Edge[]>([]);

  const [isLoadingEdges, setIsLoadingEdges] = useState(false);
  const [isPanelOpen, setIsPanelOpen] = useState(true);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(
    analyzedDocs.length > 0 ? analyzedDocs[0].id : null
  );
  const [previewDoc, setPreviewDoc] = useState<{ id: string; name: string } | null>(null);
  const [zoomPercent, setZoomPercent] = useState(100);
  const [docSearch, setDocSearch] = useState("");

  // 뷰 팬/줌 상태
  const viewRef = useRef({ offsetX: 0, offsetY: 0, scale: 1 });
  const isPanningRef = useRef(false);
  const panStartRef = useRef({ x: 0, y: 0, offsetX: 0, offsetY: 0 });

  // 드래그 관련 ref
  const draggingNodeRef = useRef<Node | null>(null);
  const isDraggingRef = useRef(false);
  const dragStartPosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  const selectedDoc = analyzedDocs.find((d) => d.id === selectedDocId) || analyzedDocs[0];

  // 백엔드 문서 유사도 그래프 API에서 엣지 조회 (코사인 유사도 기반, min_score=0.5 기본)
  useEffect(() => {
    let cancelled = false;

    async function loadGraph() {
      if (analyzedDocs.length === 0) {
        edgesRef.current = [];
        return;
      }

      setIsLoadingEdges(true);
      const res = await getDocumentGraphApi(workspaceId);
      if (cancelled) return;

      if (res.status === "success") {
        // API의 nodes 기준(=file_kind=document 전체)과 화면에 실제 그려지는
        // analyzedDocs가 완전히 일치하지 않을 수 있어, 양쪽에 다 존재하는
        // 문서 쌍만 엣지로 사용한다.
        const knownIds = new Set(analyzedDocs.map((d) => d.id));
        edgesRef.current = res.edges
          .filter((e) => knownIds.has(e.source_file_id) && knownIds.has(e.target_file_id))
          .map((e) => ({
            a: e.source_file_id,
            b: e.target_file_id,
            // 백엔드가 similarity_score를 문자열로 내려줄 때가 있어서, 숫자로 안 바꾸면
            // "0.4 + strength" 같은 연산에서 문자열 이어붙이기가 일어나 NaN이 퍼진다.
            strength: Number(e.similarity_score),
          }));
      } else {
        edgesRef.current = [];
      }
      setIsLoadingEdges(false);
    }

    loadGraph();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, analyzedIds]);

  // 노드 초기화 및 위치 설정 (기존 위치 유지, 새 노드는 원형으로 흩뿌려 배치)
  useEffect(() => {
    if (analyzedDocs.length === 0) return;

    const canvas = canvasRef.current;
    const width = canvas?.parentElement?.clientWidth || 600;
    const height = canvas?.parentElement?.clientHeight || 400;

    nodesRef.current = analyzedDocs.map((doc, idx) => {
      const existing = nodesRef.current.find((n) => n.id === doc.id);
      if (existing) return existing;

      const angle = (idx / analyzedDocs.length) * 2 * Math.PI;
      const radiusDist = Math.min(width, height) * 0.3;

      return {
        id: doc.id,
        name: doc.name,
        group: getExtGroup(doc.name),
        x: width / 2 + radiusDist * Math.cos(angle) + (Math.random() - 0.5) * 40,
        y: height / 2 + radiusDist * Math.sin(angle) + (Math.random() - 0.5) * 40,
        vx: 0,
        vy: 0,
        radius: 10,
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analyzedIds]);

  // Canvas 렌더링 및 force-directed 물리 시뮬레이션
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    const REPEL_K = 1000;
    const SPRING_K = 0.02;
    const REST_LENGTH = 90;
    const BASE_RADIUS = 10;
    const HOVER_RADIUS = 16;
    // 처음 배치된 노드끼리 우연히 가까우면 반발력이 순간적으로 튀는데(distSq가 작을수록
    // force가 급증), 그걸 그대로 속도에 실으면 시작하자마자 사방으로 튕겨나가는 것처럼
    // 보인다 - 프레임당 속도 상한을 둬서 그 첫 튕김 폭을 눌러준다.
    const MAX_SPEED = 10;

    const render = () => {
      const parent = canvas.parentElement;
      if (parent) {
        const dpr = window.devicePixelRatio || 1;
        const cssWidth = parent.clientWidth;
        const cssHeight = parent.clientHeight;
        if (canvas.width !== cssWidth * dpr || canvas.height !== cssHeight * dpr) {
          canvas.width = cssWidth * dpr;
          canvas.height = cssHeight * dpr;
          canvas.style.width = `${cssWidth}px`;
          canvas.style.height = `${cssHeight}px`;
        }
      }

      const dpr = window.devicePixelRatio || 1;
      const width = canvas.width / dpr;
      const height = canvas.height / dpr;
      const nodes = nodesRef.current;
      const edges = edgesRef.current;

      // 노드 크기는 다 동일하게 고정 (커지는 건 호버할 때 렌더링 단계에서만)
      nodes.forEach((n) => {
        n.radius = BASE_RADIUS;
      });

      // 1. 노드 간 반발력 (일정 거리 안에서만 - 너무 멀어지는 것 방지, 중앙 수렴력은 없음)
      const REPEL_RANGE = 240;
      for (let i = 0; i < nodes.length; i++) {
        const nodeA = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const nodeB = nodes[j];
          const dx = nodeB.x - nodeA.x;
          const dy = nodeB.y - nodeA.y;
          const distSq = Math.max(dx * dx + dy * dy, 1);
          const dist = Math.sqrt(distSq);
          if (dist >= REPEL_RANGE) continue;

          const force = REPEL_K / distSq;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;

          if (draggingNodeRef.current !== nodeA) {
            nodeA.vx -= fx;
            nodeA.vy -= fy;
          }
          if (draggingNodeRef.current !== nodeB) {
            nodeB.vx += fx;
            nodeB.vy += fy;
          }
        }
      }

      // 2. 연결된 노드끼리 스프링 인력 (연관성 강할수록 더 세게 당김)
      edges.forEach((edge) => {
        const nodeA = nodes.find((n) => n.id === edge.a);
        const nodeB = nodes.find((n) => n.id === edge.b);
        if (!nodeA || !nodeB) return;

        const dx = nodeB.x - nodeA.x;
        const dy = nodeB.y - nodeA.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const restLength = REST_LENGTH * (1 - edge.strength * 0.5);
        const force = SPRING_K * (dist - restLength) * (0.4 + edge.strength);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (draggingNodeRef.current !== nodeA) {
          nodeA.vx += fx;
          nodeA.vy += fy;
        }
        if (draggingNodeRef.current !== nodeB) {
          nodeB.vx -= fx;
          nodeB.vy -= fy;
        }
      });

      // 3. 전체 그래프 무게중심만 화면 중앙 쪽으로 아주 약하게 재정렬 (개별 노드 수렴 아님)
      if (nodes.length > 0) {
        const cx = nodes.reduce((s, n) => s + n.x, 0) / nodes.length;
        const cy = nodes.reduce((s, n) => s + n.y, 0) / nodes.length;
        const nudgeX = (width / 2 - cx) * 0.002;
        const nudgeY = (height / 2 - cy) * 0.002;
        nodes.forEach((n) => {
          if (draggingNodeRef.current !== n) {
            n.vx += nudgeX;
            n.vy += nudgeY;
          }
        });
      }

      // 3-1. 화면 중앙에서 너무 멀어진 노드만 살짝 되돌림 (연결 없는 노드가 끝없이 밀려나가는 것 방지)
      const maxDist = Math.min(width, height) * 0.42;
      nodes.forEach((n) => {
        if (draggingNodeRef.current === n) return;
        const dx = n.x - width / 2;
        const dy = n.y - height / 2;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        if (dist > maxDist) {
          const pull = (dist - maxDist) * 0.02;
          n.vx -= (dx / dist) * pull;
          n.vy -= (dy / dist) * pull;
        }
      });

      // 4. 감쇄 및 위치 업데이트 (감쇄를 좀 더 세게 줘서 초반에 통통 튀는 느낌을 줄인다)
      nodes.forEach((n) => {
        n.vx *= 0.72;
        n.vy *= 0.72;
        const speed = Math.hypot(n.vx, n.vy);
        if (speed > MAX_SPEED) {
          n.vx = (n.vx / speed) * MAX_SPEED;
          n.vy = (n.vy / speed) * MAX_SPEED;
        }
        if (draggingNodeRef.current !== n) {
          n.x += n.vx;
          n.y += n.vy;
        }
      });

      // --- 렌더링 ---
      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);

      // 점 그리드 배경
      const { offsetX, offsetY, scale } = viewRef.current;
      const gridSize = 28 * scale;
      ctx.fillStyle = "rgba(148, 163, 184, 0.12)";
      for (let gx = offsetX % gridSize; gx < width; gx += gridSize) {
        for (let gy = offsetY % gridSize; gy < height; gy += gridSize) {
          ctx.beginPath();
          ctx.arc(gx, gy, 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      ctx.translate(offsetX, offsetY);
      ctx.scale(scale, scale);

      // 호버 중이면 호버 노드, 아니면 선택된 노드를 기준으로 연결 강조
      const focusNodeId = hoveredNodeId || selectedDocId;
      const activeNeighborIds = new Set<string>();
      if (focusNodeId) {
        edges.forEach((e) => {
          if (e.a === focusNodeId) activeNeighborIds.add(e.b);
          if (e.b === focusNodeId) activeNeighborIds.add(e.a);
        });
      }

      // 엣지 그리기 (포커스 노드와 연결된 선만 눈에 띄게, 나머지는 흐리게)
      edges.forEach((edge) => {
        const nodeA = nodes.find((n) => n.id === edge.a);
        const nodeB = nodes.find((n) => n.id === edge.b);
        if (!nodeA || !nodeB) return;

        const isRelatedToFocus =
          !focusNodeId || edge.a === focusNodeId || edge.b === focusNodeId;

        ctx.beginPath();
        ctx.moveTo(nodeA.x, nodeA.y);
        ctx.lineTo(nodeB.x, nodeB.y);

        if (focusNodeId && isRelatedToFocus) {
          ctx.strokeStyle = `rgba(165, 180, 252, ${0.55 + edge.strength * 0.4})`;
          ctx.lineWidth = 2 + edge.strength * 2.5;
        } else {
          // 아무것도 선택 안 했을 때도 선이 기본적으로 보이게 최소 알파를 올려둠
          // (예전엔 포커스 대상이 아닌 선은 0.04라 사실상 안 보였음)
          const alpha = isRelatedToFocus ? 0.15 + edge.strength * 0.6 : 0.12 + edge.strength * 0.25;
          ctx.strokeStyle = `rgba(129, 140, 248, ${alpha})`;
          ctx.lineWidth = 1;
        }
        ctx.stroke();
      });

      // 노드 그리기
      nodes.forEach((node) => {
        const isSelected = selectedDocId === node.id;
        const isHovered = hoveredNodeId === node.id;
        const isFocused = focusNodeId === node.id;
        const isNeighborOfFocus = activeNeighborIds.has(node.id);
        const isDimmed = focusNodeId ? !isFocused && !isNeighborOfFocus : false;
        const displayRadius = isHovered ? HOVER_RADIUS : node.radius;

        ctx.save();
        ctx.globalAlpha = isDimmed ? 0.35 : 1;

        ctx.beginPath();
        ctx.arc(node.x, node.y, displayRadius, 0, Math.PI * 2);

        if (isSelected || isHovered) {
          ctx.shadowColor = "rgba(99, 102, 241, 0.9)";
          ctx.shadowBlur = 16;
        }

        ctx.fillStyle = getGroupColor(node.group);
        ctx.fill();

        if (isSelected || isHovered) {
          ctx.shadowBlur = 0;
          ctx.lineWidth = isSelected ? 2.5 : 1.5;
          ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
          ctx.stroke();
        }

        // 확대/축소를 해도 글자 크기가 화면 기준으로 일정하게 보이도록 scale의 역수를 곱한다
        // (안 그러면 ctx.scale(scale)이 걸린 채로 그려서 축소 시 라벨이 안 보일 정도로 작아짐)
        ctx.font = `${11 / scale}px -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = isSelected || isHovered ? "rgba(226, 232, 240, 0.95)" : "rgba(226, 232, 240, 0.7)";
        ctx.fillText(truncateLabel(node.name), node.x, node.y + displayRadius + 4 / scale);

        ctx.restore();
      });

      ctx.restore();

      animId = requestAnimationFrame(render);
    };

    render();

    return () => cancelAnimationFrame(animId);
  }, [selectedDocId, hoveredNodeId]);

  // 화면 좌표 -> 그래프 좌표 변환
  const toGraphCoords = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const { offsetX, offsetY, scale } = viewRef.current;
    return {
      x: (clientX - rect.left - offsetX) / scale,
      y: (clientY - rect.top - offsetY) / scale,
    };
  };

  const getNodeAt = (x: number, y: number): Node | null => {
    const nodes = nodesRef.current;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const node = nodes[i];
      const dx = x - node.x;
      const dy = y - node.y;
      if (dx * dx + dy * dy <= (node.radius + 6) * (node.radius + 6)) {
        return node;
      }
    }
    return null;
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = toGraphCoords(e.clientX, e.clientY);
    const node = getNodeAt(x, y);

    if (node) {
      draggingNodeRef.current = node;
      isDraggingRef.current = false;
      dragStartPosRef.current = { x: e.clientX, y: e.clientY };
    } else {
      isPanningRef.current = true;
      panStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        offsetX: viewRef.current.offsetX,
        offsetY: viewRef.current.offsetY,
      };
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (draggingNodeRef.current) {
      const moveDist = Math.hypot(e.clientX - dragStartPosRef.current.x, e.clientY - dragStartPosRef.current.y);
      if (moveDist > 3) isDraggingRef.current = true;
      const { x, y } = toGraphCoords(e.clientX, e.clientY);
      draggingNodeRef.current.x = x;
      draggingNodeRef.current.y = y;
      return;
    }

    if (isPanningRef.current) {
      viewRef.current.offsetX = panStartRef.current.offsetX + (e.clientX - panStartRef.current.x);
      viewRef.current.offsetY = panStartRef.current.offsetY + (e.clientY - panStartRef.current.y);
      return;
    }

    const { x, y } = toGraphCoords(e.clientX, e.clientY);
    const hovered = getNodeAt(x, y);
    setHoveredNodeId(hovered ? hovered.id : null);
  };

  const handleMouseUp = () => {
    if (draggingNodeRef.current) {
      if (!isDraggingRef.current) {
        setSelectedDocId(draggingNodeRef.current.id);
      }
      draggingNodeRef.current = null;
    }
    isPanningRef.current = false;
  };

  // 특정 화면 좌표(pivot)를 기준으로 확대/축소 - 지정 안 하면 캔버스 중앙 기준
  // (휠 줌과 +/- 버튼 줌이 이 함수 하나를 공유한다)
  const applyZoom = (rawScale: number, pivot?: { x: number; y: number }) => {
    const canvas = canvasRef.current;
    const { offsetX, offsetY, scale } = viewRef.current;
    const newScale = Math.min(Math.max(rawScale, 0.3), 3);
    const px = pivot?.x ?? (canvas ? canvas.clientWidth / 2 : 0);
    const py = pivot?.y ?? (canvas ? canvas.clientHeight / 2 : 0);

    viewRef.current.offsetX = px - ((px - offsetX) / scale) * newScale;
    viewRef.current.offsetY = py - ((py - offsetY) / scale) * newScale;
    viewRef.current.scale = newScale;
    setZoomPercent(Math.round(newScale * 100));
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    applyZoom(viewRef.current.scale * zoomFactor, {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  const handleResetView = () => {
    viewRef.current = { offsetX: 0, offsetY: 0, scale: 1 };
    setZoomPercent(100);
  };

  const hoveredNode = nodesRef.current.find((n) => n.id === hoveredNodeId);
  const relatedToSelected = selectedDocId
    ? edgesRef.current
        .filter((e) => e.a === selectedDocId || e.b === selectedDocId)
        .sort((a, b) => b.strength - a.strength)
        .map((e) => {
          const otherId = e.a === selectedDocId ? e.b : e.a;
          return { doc: analyzedDocs.find((d) => d.id === otherId), strength: e.strength };
        })
        .filter((x) => x.doc)
    : [];

  const presentGroups = Array.from(new Set(analyzedDocs.map((d) => getExtGroup(d.name)))).sort(
    (a, b) => a - b
  );

  const filteredDocs = docSearch.trim()
    ? analyzedDocs.filter((d) => d.name.toLowerCase().includes(docSearch.trim().toLowerCase()))
    : analyzedDocs;

  return (
    <div className="flex h-full w-full flex-col bg-recall-bgMain p-4 text-recall-text">
      <div className="mb-4">
        <p className="text-base font-semibold">{t.graph_title || "지식 그래프 시각화"}</p>
        <p className="text-sm text-recall-textMuted">
          {t.graph_sub || "문서 내용 유사도 기반 지식 네트워크"}
          {isLoadingEdges && " · 연관성 분석 중..."}
        </p>
      </div>

      {analyzedDocs.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-recall-border bg-recall-bgSoft">
          <p className="text-base text-recall-textMuted">{t.graph_no_docs || "분석 완료된 문서가 없습니다."}</p>
        </div>
      ) : (
        <div className="relative flex-1 overflow-hidden rounded-xl border border-recall-border bg-recall-bgSoft">
          {/* 그래프는 항상 전체 화면을 쓰고, 문서 목록/줌 컨트롤은 그 위에 떠 있는 패널로 처리 */}
          <canvas
            ref={canvasRef}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onWheel={handleWheel}
            onMouseLeave={() => {
              draggingNodeRef.current = null;
              isPanningRef.current = false;
              setHoveredNodeId(null);
            }}
            className="h-full w-full cursor-grab active:cursor-grabbing"
          />

          {hoveredNode && (
            <div
              style={{
                position: "absolute",
                left: `${hoveredNode.x * viewRef.current.scale + viewRef.current.offsetX}px`,
                top: `${
                  (hoveredNode.y + hoveredNode.radius + 8) * viewRef.current.scale +
                  viewRef.current.offsetY
                }px`,
                transform: "translateX(-50%)",
              }}
              className="pointer-events-none z-20 flex flex-col items-center"
            >
              <div className="h-0 w-0 border-x-4 border-x-transparent border-b-4 border-b-recall-bgMain" />
              <div className="whitespace-nowrap rounded-md border border-recall-border bg-recall-bgMain px-2.5 py-1 text-center shadow-xl">
                <p className="text-xs font-semibold text-recall-text">{hoveredNode.name}</p>
              </div>
            </div>
          )}

          {presentGroups.length > 0 && (
            <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex flex-wrap gap-2.5 rounded-lg border border-recall-border bg-recall-bgMain/85 px-3 py-2 backdrop-blur-sm">
              {presentGroups.map((group) => (
                <div key={group} className="flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 flex-shrink-0 rounded-full"
                    style={{ background: getGroupColor(group) }}
                  />
                  <span className="text-xs text-recall-textMuted">{GROUP_LABELS[group] ?? "기타"}</span>
                </div>
              ))}
            </div>
          )}

          {/* 문서 목록 패널 + 토글/줌 툴바 - 오른쪽에 같이 붙여서 한 덩어리로 보이게 */}
          <div className="absolute right-3 top-3 z-30 flex flex-row-reverse items-start gap-2">
            <div className="flex flex-col gap-2">
              <button
                onClick={() => setIsPanelOpen((v) => !v)}
                title={isPanelOpen ? "문서 목록 닫기" : "문서 목록 열기"}
                className={`flex h-9 w-9 items-center justify-center rounded-xl shadow-lg transition ${
                  isPanelOpen
                    ? "bg-recall-accent text-white"
                    : "border border-recall-border bg-recall-bgMain/95 text-recall-textMuted backdrop-blur-sm hover:text-recall-text"
                }`}
              >
                <MenuIcon size={16} />
              </button>

              <div className="flex flex-col items-center gap-1 rounded-xl border border-recall-border bg-recall-bgMain/95 p-1 shadow-lg backdrop-blur-sm">
                <button
                  onClick={() => applyZoom(viewRef.current.scale * 1.2)}
                  title="확대"
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
                >
                  <PlusIcon size={14} />
                </button>
                <span className="w-full py-0.5 text-center text-[11px] tabular-nums text-recall-textMuted">
                  {zoomPercent}%
                </span>
                <button
                  onClick={() => applyZoom(viewRef.current.scale / 1.2)}
                  title="축소"
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
                >
                  <MinusIcon size={14} />
                </button>
                <div className="my-0.5 h-px w-5 bg-recall-border" />
                <button
                  onClick={handleResetView}
                  title="보기 초기화"
                  className="flex h-7 w-7 items-center justify-center rounded-lg text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
                >
                  <RepeatIcon size={13} />
                </button>
              </div>
            </div>

            {isPanelOpen && (
              <div className="flex max-h-[calc(100vh-8rem)] w-72 flex-col gap-3 overflow-hidden">
                <div className="flex flex-col overflow-hidden rounded-xl border border-recall-border bg-recall-bgMain/95 shadow-xl backdrop-blur-sm">
                  <div className="flex items-center justify-between border-b border-recall-border px-3.5 py-2.5">
                    <p className="text-sm font-semibold text-recall-text">
                      전체 문서 (
                      {docSearch.trim() ? `${filteredDocs.length}/${analyzedDocs.length}` : analyzedDocs.length})
                    </p>
                    <button
                      onClick={() => setIsPanelOpen(false)}
                      className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded text-recall-textMuted hover:bg-white/5 hover:text-recall-text"
                    >
                      <CloseIcon size={14} />
                    </button>
                  </div>

                  <div className="border-b border-recall-border p-2">
                    <div className="flex items-center gap-1.5 rounded-lg border border-recall-border bg-recall-bg px-2 py-1.5">
                      <SearchIcon size={13} className="flex-shrink-0 text-recall-textMuted" />
                      <input
                        value={docSearch}
                        onChange={(e) => setDocSearch(e.target.value)}
                        placeholder="문서 이름 검색"
                        className="w-full bg-transparent text-sm text-recall-text placeholder:text-recall-textMuted focus:outline-none"
                      />
                      {docSearch && (
                        <button
                          onClick={() => setDocSearch("")}
                          className="flex-shrink-0 text-recall-textMuted hover:text-recall-text"
                        >
                          <CloseIcon size={12} />
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="max-h-48 space-y-0.5 overflow-y-auto p-1.5">
                    {filteredDocs.length === 0 ? (
                      <p className="px-2 py-3 text-center text-xs text-recall-textMuted">검색 결과가 없어요</p>
                    ) : (
                      filteredDocs.map((doc) => {
                        const isSelected = doc.id === selectedDoc?.id;
                        return (
                          <button
                            key={doc.id}
                            onClick={() => setSelectedDocId(doc.id)}
                            className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition ${
                              isSelected ? "bg-recall-accent/15 text-recall-accent" : "text-recall-text hover:bg-white/5"
                            }`}
                          >
                            <span
                              className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
                              style={{ background: getGroupColor(getExtGroup(doc.name)) }}
                            />
                            <span className="truncate">{doc.name}</span>
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>

                {selectedDoc && (
                  <div className="rounded-xl border border-recall-border bg-recall-bgMain/95 p-3.5 shadow-xl backdrop-blur-sm">
                    <p className="truncate text-sm font-semibold text-recall-text">{selectedDoc.name}</p>
                    <p className="mt-1 text-xs text-recall-textMuted">
                      {new Date(selectedDoc.uploadedAt).toLocaleDateString("ko-KR")}
                    </p>

                    <p className="mt-2.5 text-xs font-medium text-recall-textMuted">
                      연관 문서 {relatedToSelected.length}개
                    </p>
                    {relatedToSelected.length === 0 ? (
                      <p className="mt-0.5 text-xs text-recall-textMuted/70">연관된 문서가 없어요</p>
                    ) : (
                      <div className="mt-1.5 space-y-1">
                        {relatedToSelected.map(({ doc, strength }) => (
                          <button
                            key={doc!.id}
                            onClick={() => setSelectedDocId(doc!.id)}
                            className="flex w-full items-center justify-between rounded-lg border border-recall-border bg-recall-bg px-2 py-1 text-left text-xs hover:border-recall-accent/50"
                          >
                            <span className="truncate text-recall-text">{doc!.name}</span>
                            <span className="ml-2 flex-shrink-0 text-recall-textMuted">
                              {Math.round(strength * 100)}%
                            </span>
                          </button>
                        ))}
                      </div>
                    )}

                    <button
                      onClick={() => setPreviewDoc({ id: selectedDoc.id, name: selectedDoc.name })}
                      className="mt-3 flex w-full items-center justify-center rounded-lg bg-recall-accent py-2 text-sm font-medium text-white hover:opacity-90"
                    >
                      문서 내용 보기 →
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {previewDoc && (
        <DocumentPreviewModal
          workspaceId={workspaceId}
          documentId={previewDoc.id}
          documentName={previewDoc.name}
          onClose={() => setPreviewDoc(null)}
          t={t}
        />
      )}
    </div>
  );
}
