import { useEffect, useRef, useState } from "react";
import { AnalyzedDocument } from "../types";
import { getDocumentGraphApi } from "../services/document";
import { SparklesIcon } from "./icons";
import DocumentPreviewModal from "./DocumentPreviewModal";

interface GraphViewProps {
  workspaceId: string;
  documents: AnalyzedDocument[];
  t: any;
}

interface Node {
  id: string;
  name: string;
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
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(
    analyzedDocs.length > 0 ? analyzedDocs[0].id : null
  );
  const [previewDoc, setPreviewDoc] = useState<{ id: string; name: string } | null>(null);

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
    const REPEL_K = 1600;
    const SPRING_K = 0.02;
    const REST_LENGTH = 90;
    const BASE_RADIUS = 10;
    const HOVER_RADIUS = 16;

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

      // 4. 감쇄 및 위치 업데이트
      nodes.forEach((n) => {
        n.vx *= 0.82;
        n.vy *= 0.82;
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
          const alpha = isRelatedToFocus ? 0.15 + edge.strength * 0.6 : 0.04;
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

        ctx.fillStyle = isSelected ? "#818CF8" : isHovered ? "#6366F1" : "#4F46E5";
        ctx.fill();

        if (isSelected) {
          ctx.shadowBlur = 0;
          ctx.lineWidth = 2.5;
          ctx.strokeStyle = "rgba(199, 210, 254, 0.9)";
          ctx.stroke();
        }
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

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const { offsetX, offsetY, scale } = viewRef.current;
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    const newScale = Math.min(Math.max(scale * zoomFactor, 0.3), 3);

    // 마우스 포인터 위치를 기준으로 확대/축소
    viewRef.current.offsetX = mouseX - ((mouseX - offsetX) / scale) * newScale;
    viewRef.current.offsetY = mouseY - ((mouseY - offsetY) / scale) * newScale;
    viewRef.current.scale = newScale;
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
        <div className="grid flex-1 grid-cols-3 gap-4 overflow-hidden">
          <div className="col-span-2 relative flex flex-col rounded-xl border border-recall-border bg-recall-bgSoft overflow-hidden">
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
          </div>

          <div className="flex flex-col gap-4 overflow-hidden">
            <div className="rounded-xl border border-recall-border bg-recall-bgSoft p-4">
              <p className="mb-3 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-recall-textMuted">
                <SparklesIcon size={14} className="text-recall-accent" />
                연관 문서 {selectedDoc ? `- ${selectedDoc.name}` : ""}
              </p>
              {relatedToSelected.length === 0 ? (
                <p className="text-sm text-recall-textMuted">연관된 문서가 없습니다.</p>
              ) : (
                <div className="space-y-1.5">
                  {relatedToSelected.map(({ doc, strength }) => (
                    <button
                      key={doc!.id}
                      onClick={() => setSelectedDocId(doc!.id)}
                      className="flex w-full items-center justify-between rounded-lg border border-recall-border bg-recall-bgMain px-2.5 py-1.5 text-left text-sm hover:border-recall-accent/50"
                    >
                      <span className="truncate text-recall-text">{doc!.name}</span>
                      <span className="ml-2 flex-shrink-0 text-[11px] text-recall-textMuted">
                        {Math.round(strength * 100)}%
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="flex-1 rounded-xl border border-recall-border bg-recall-bgSoft p-4 overflow-y-auto">
              <p className="mb-3 text-sm font-semibold text-recall-textMuted uppercase">
                전체 문서 목록 ({analyzedDocs.length})
              </p>

              <div className="space-y-2">
                {analyzedDocs.map((doc) => {
                  const isSelected = doc.id === selectedDoc?.id;

                  return (
                    <div
                      key={doc.id}
                      onClick={() => setSelectedDocId(doc.id)}
                      className={`flex cursor-pointer items-center justify-between rounded-xl border p-3 text-sm transition ${
                        isSelected
                          ? "border-recall-accent bg-recall-accent/10 shadow-sm"
                          : "border-recall-border bg-recall-bgMain hover:border-recall-accent/50"
                      }`}
                    >
                      <span className="truncate font-semibold text-recall-text pr-2">{doc.name}</span>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setPreviewDoc({ id: doc.id, name: doc.name });
                        }}
                        className="shrink-0 rounded-lg bg-recall-accent/15 px-2.5 py-1.5 text-xs font-semibold text-recall-accent hover:bg-recall-accent hover:text-white transition"
                      >
                        상세보기 →
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {previewDoc && (
        <DocumentPreviewModal
          workspaceId={workspaceId}
          documentId={previewDoc.id}
          documentName={previewDoc.name}
          onClose={() => setPreviewDoc(null)}
        />
      )}
    </div>
  );
}
