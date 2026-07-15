import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import { AnalyzedDocument } from "../types";
import { CloseIcon, DocumentIcon } from "./icons";

interface GraphViewProps {
  documents: AnalyzedDocument[];
  onGoToAnalysis: (documentId: string) => void;
}

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  group: number;
}

interface GraphLink {
  source: string;
  target: string;
}

// 그룹은 진짜 임베딩 유사도 전까지 "확장자" 기준 임시 분류
// 나중에 승주 쪽 임베딩/유사도 API 들어오면 이 부분을 실제 유사도 그룹으로 교체
const EXT_GROUP: Record<string, number> = { PDF: 1, DOCX: 2, TXT: 3 };
const GROUP_COLORS = ["#7c6af7", "#4caf82", "#e8a838", "#94a3b8"]; // PDF, DOCX, TXT, 기타
const GROUP_LABELS: Record<number, string> = { 1: "PDF", 2: "DOCX", 3: "TXT", 4: "기타" };

function getExt(filename: string): string {
  return filename.split(".").pop()?.toUpperCase() ?? "";
}

function getGroupColor(group: number): string {
  return GROUP_COLORS[(group - 1) % GROUP_COLORS.length];
}

function readCssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value ? `rgb(${value})` : fallback;
}

// 그래프 캔버스 - d3-force로 노드/링크 배치, 드래그/줌 지원
// svgRef는 부모(GraphView)가 만들어서 넘겨줌 - 줌 버튼(+/-/리셋)이 같은 svg를 조작해야 하므로
function GraphCanvas({
  svgRef,
  nodes,
  links,
  onSelect,
  zoomRef,
  onZoomChange,
}: {
  svgRef: React.RefObject<SVGSVGElement>;
  nodes: GraphNode[];
  links: GraphLink[];
  onSelect: (id: string | null) => void;
  zoomRef: React.MutableRefObject<d3.ZoomBehavior<SVGSVGElement, unknown> | null>;
  onZoomChange: (scale: number) => void;
}) {
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;

    const borderColor = readCssVar("--recall-border", "rgb(200 200 200)");
    const textColor = readCssVar("--recall-text", "rgb(20 20 20)");

    const g = svg.append("g");

    const simulation = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink<GraphNode, d3.SimulationLinkDatum<GraphNode>>(
            links as unknown as d3.SimulationLinkDatum<GraphNode>[]
          )
          .id((d) => d.id)
          .distance(90)
      )
      .force("charge", d3.forceManyBody().strength(-220))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(26));

    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", borderColor)
      .attr("stroke-width", 1.2);

    const node = g
      .append("g")
      .selectAll<SVGGElement, GraphNode>("g")
      .data(nodes)
      .join("g")
      .attr("cursor", "pointer")
      .call(
        d3
          .drag<SVGGElement, GraphNode>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      )
      .on("click", (_event, d) => onSelect(d.id));

    node
      .append("circle")
      .attr("r", 18)
      .attr("fill", (d) => getGroupColor(d.group))
      .attr("fill-opacity", 0.85);

    node
      .append("text")
      .text((d) => d.label)
      .attr("text-anchor", "middle")
      .attr("dy", 32)
      .attr("font-size", 10)
      .attr("fill", textColor)
      .style("pointer-events", "none");

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
        onZoomChange(event.transform.k);
      });

    svg.call(zoom);
    zoomRef.current = zoom;

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, links]);

  return <svg ref={svgRef} width="100%" height="100%" />;
}

// 우측 패널 - 전체 문서 목록
function DocumentList({
  documents,
  selected,
  onSelect,
}: {
  documents: AnalyzedDocument[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="rounded-lg border border-recall-border bg-recall-bgSoft p-3 shadow-lg">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-recall-textMuted">
        문서 목록
      </p>
      <div className="max-h-60 space-y-1 overflow-y-auto">
        {documents.map((doc) => {
          const group = EXT_GROUP[getExt(doc.name)] ?? 4;
          return (
            <button
              key={doc.id}
              onClick={() => onSelect(doc.id)}
              className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs ${
                selected === doc.id ? "bg-recall-accent/10" : "hover:bg-white/5"
              }`}
            >
              <span
                className="h-2 w-2 flex-shrink-0 rounded-full"
                style={{ background: getGroupColor(group) }}
              />
              <span className="min-w-0 flex-1 truncate text-recall-text">{doc.name}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// 우측 패널 - 선택한 문서 상세 + 연결된 문서 + 분석 보기 이동
function SelectedDocument({
  doc,
  connectedDocs,
  onGoToAnalysis,
}: {
  doc: AnalyzedDocument;
  connectedDocs: AnalyzedDocument[];
  onGoToAnalysis: () => void;
}) {
  return (
    <div className="rounded-lg border border-recall-border bg-recall-bgSoft p-3 shadow-lg">
      <div className="mb-2 flex items-start gap-2">
        <DocumentIcon size={15} className="mt-0.5 flex-shrink-0 text-recall-textMuted" />
        <p className="min-w-0 flex-1 truncate text-sm font-medium text-recall-text">{doc.name}</p>
      </div>

      <p className="mb-2 text-xs text-recall-textMuted">
        연결된 문서 {connectedDocs.length}개 (키워드 공유 기준 · 임시)
      </p>
      {connectedDocs.length > 0 && (
        <ul className="mb-3 space-y-1">
          {connectedDocs.map((d) => (
            <li key={d.id} className="truncate text-xs text-recall-text">
              · {d.name}
            </li>
          ))}
        </ul>
      )}

      <button
        onClick={onGoToAnalysis}
        className="w-full rounded-lg border border-recall-accent px-3 py-1.5 text-xs text-recall-accent hover:bg-recall-accent/10"
      >
        문서 분석에서 보기
      </button>
    </div>
  );
}

export default function GraphView({ documents, onGoToAnalysis }: GraphViewProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [showPanel, setShowPanel] = useState(true);
  const [zoomLevel, setZoomLevel] = useState(1);
  const svgRef = useRef<SVGSVGElement>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  // 분석이 끝난 문서만 그래프에 올림 (키워드가 있어야 연결선을 만들 수 있어서)
  const readyDocs = documents.filter((d) => d.status === "done");
  // readyDocs를 문서 id로 묶어서 의존성 비교 - documents 배열 자체가 매 렌더마다 새 참조라도
  // 실제 내용(어떤 문서가 분석 완료됐는지)이 안 바뀌었으면 nodes/links를 다시 안 만들게 함
  const readyDocsKey = readyDocs.map((d) => d.id).join(",");

  // nodes/links를 고정해두지 않으면 줌/선택 등 다른 state가 바뀔 때마다 이 값들이 새로 생성되고,
  // 그 여파로 GraphCanvas의 useEffect가 매번 재실행되면서 줌이 계속 초기 상태로 리셋돼버림
  const nodes: GraphNode[] = useMemo(
    () =>
      readyDocs.map((doc) => ({
        id: doc.id,
        label: doc.name,
        group: EXT_GROUP[getExt(doc.name)] ?? 4,
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [readyDocsKey]
  );

  // 연결선: 진짜 유사도 API 들어오기 전까지, 키워드를 하나라도 공유하는 문서끼리 임시로 연결
  // TODO: 임베딩 유사도 API 연동되면 이 로직을 실제 유사도 기반 연결로 교체
  const links: GraphLink[] = useMemo(() => {
    const result: GraphLink[] = [];
    for (let i = 0; i < readyDocs.length; i++) {
      for (let j = i + 1; j < readyDocs.length; j++) {
        const a = readyDocs[i];
        const b = readyDocs[j];
        const shared = (a.keywords ?? []).some((kw) => (b.keywords ?? []).includes(kw));
        if (shared) result.push({ source: a.id, target: b.id });
      }
    }
    return result;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readyDocsKey]);

  function handleSelect(id: string | null) {
    setSelected(id);
    if (id) setShowPanel(true);
  }

  const selectedDoc = readyDocs.find((d) => d.id === selected) ?? null;
  const connectedIds = links
    .filter((l) => l.source === selected || l.target === selected)
    .map((l) => (l.source === selected ? l.target : l.source));
  const connectedDocs = readyDocs.filter((d) => connectedIds.includes(d.id));

  const usedGroups = Array.from(new Set(nodes.map((n) => n.group))).sort();

  function zoomBy(factor: number) {
    if (!zoomRef.current || !svgRef.current) return;
    d3.select(svgRef.current).transition().call(zoomRef.current.scaleBy as any, factor);
  }

  function zoomReset() {
    if (!zoomRef.current || !svgRef.current) return;
    d3.select(svgRef.current)
      .transition()
      .call(zoomRef.current.transform as any, d3.zoomIdentity);
  }

  return (
    <div className="relative h-full w-full bg-recall-bgMain">
      <div className="absolute inset-0 overflow-hidden rounded-xl border border-recall-border">
        {readyDocs.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-recall-textMuted">
              분석이 끝난 문서가 있어야 그래프에 표시돼요. (문서 분석에서 먼저 업로드해보세요)
            </p>
          </div>
        ) : (
          <GraphCanvas
            svgRef={svgRef}
            nodes={nodes}
            links={links}
            onSelect={handleSelect}
            zoomRef={zoomRef}
            onZoomChange={setZoomLevel}
          />
        )}
      </div>

      <div className="absolute left-4 top-4 z-10">
        <p className="text-sm font-semibold text-recall-text">그래프 시각화</p>
        <p className="mt-0.5 text-xs text-recall-textMuted">
          문서 유형 · 키워드 공유 기반 연관성 시각화 (임시)
        </p>
      </div>

      <div className="absolute right-4 top-4 z-10 flex flex-col gap-1.5">
        <button
          onClick={() => setShowPanel((v) => !v)}
          className={`flex h-8 w-8 items-center justify-center rounded-lg border shadow-sm ${
            showPanel
              ? "border-recall-accent bg-recall-accent text-white"
              : "border-recall-border bg-recall-bgSoft text-recall-textMuted hover:bg-white/5"
          }`}
          title="문서 목록"
        >
          <DocumentIcon size={14} />
        </button>
        <button
          onClick={() => zoomBy(1.3)}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-recall-border bg-recall-bgSoft text-sm font-bold text-recall-textMuted shadow-sm hover:bg-white/5"
        >
          +
        </button>
        <div className="flex h-6 w-8 items-center justify-center rounded-lg border border-recall-border bg-recall-bgSoft text-xs text-recall-textMuted">
          {Math.round(zoomLevel * 100)}%
        </div>
        <button
          onClick={() => zoomBy(0.7)}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-recall-border bg-recall-bgSoft text-sm font-bold text-recall-textMuted shadow-sm hover:bg-white/5"
        >
          −
        </button>
        <button
          onClick={zoomReset}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-recall-border bg-recall-bgSoft text-xs text-recall-textMuted shadow-sm hover:bg-white/5"
        >
          ↺
        </button>
      </div>

      {usedGroups.length > 0 && (
        <div className="absolute bottom-4 left-4 z-10 flex gap-3 rounded-lg border border-recall-border bg-recall-bgSoft/90 px-3 py-2 backdrop-blur-sm">
          {usedGroups.map((group) => (
            <div key={group} className="flex items-center gap-1.5">
              <div className="h-2 w-2 rounded-full" style={{ background: getGroupColor(group) }} />
              <span className="text-xs text-recall-textMuted">{GROUP_LABELS[group]}</span>
            </div>
          ))}
        </div>
      )}

      {showPanel && readyDocs.length > 0 && (
        <div className="absolute right-16 top-4 z-10 flex w-56 flex-col gap-3">
          <div className="flex justify-end">
            <button
              onClick={() => {
                setShowPanel(false);
                setSelected(null);
              }}
              className="flex h-6 w-6 items-center justify-center rounded-lg border border-recall-border bg-recall-bgSoft text-recall-textMuted hover:text-recall-text"
            >
              <CloseIcon size={12} />
            </button>
          </div>
          <DocumentList documents={readyDocs} selected={selected} onSelect={handleSelect} />
          {selectedDoc && (
            <SelectedDocument
              doc={selectedDoc}
              connectedDocs={connectedDocs}
              onGoToAnalysis={() => onGoToAnalysis(selectedDoc.id)}
            />
          )}
        </div>
      )}
    </div>
  );
}