import { useEffect } from 'react'
import type React from 'react'
import * as d3 from 'd3'

type Node = { id: string; label: string; group: number; size: number }  
type Link = { source: string; target: string; value: number }

type Props = {
  nodes: Node[]
  links: Link[]
  isDark: boolean
  getGroupColor: (group: number) => string
  onSelect: (id: string) => void
  onZoomChange: (level: number) => void
  zoomRef: React.MutableRefObject<any>
  svgRef: React.RefObject<SVGSVGElement | null>
}

export default function GraphCanvas({ nodes, links, isDark, getGroupColor, onSelect, onZoomChange, zoomRef, svgRef }: Props) {
  //isDark 바뀔때마다 그래프 다시 그리기
  useEffect(() => {
    if (!svgRef.current) return
    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight

    const lineColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.08)'
    const textColor = isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.35)'
    const textHoverColor = isDark ? '#ffffff' : '#111111'

    //기존 SVG 내용 전부 지우고 새로 그림
    d3.select(svgRef.current).selectAll('*').remove()
    const svg = d3.select(svgRef.current)

    //줌/패닝 적용될 그룹 컨테이너
    const g = svg.append('g')

    //줌 설정
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
        onZoomChange(Math.round(event.transform.k * 100) / 100)
      })
    svg.call(zoom)
    zoomRef.current = zoom //외부에서 줌 인/아웃 버튼으로 제어

    // svg 클릭 시 선택 해제 (노드 클릭은 별도 처리)
    svg.on('click', (event) => {
      if (event.target === svgRef.current) {
        onSelect('')
      }
    })

      //노드들이 퍼지도록 힘 기반 레이아웃 적용
    const simulation = d3.forceSimulation(nodes as any)
      .force('link', d3.forceLink(links as any).id((d: any) => d.id).distance(25))
      .force('charge', d3.forceManyBody().strength(-8))  //노드끼리 밀어내는 힘
      .force('collision', d3.forceCollide(6))            //노드 겹침 방지
      .force('x', d3.forceX(width / 2).strength(0.03))   //가운데로 모으는 힘 (x)
      .force('y', d3.forceY(height / 2).strength(0.03))  //가운데로 모으는 힘 (y)

    // 글로우 필터 (호버 시 선택 노드에 적용)
    const defs = svg.append('defs')
    const filter = defs.append('filter').attr('id', 'glow')
    filter.append('feGaussianBlur').attr('stdDeviation', '6').attr('result', 'coloredBlur')
    const feMerge = filter.append('feMerge')
    feMerge.append('feMergeNode').attr('in', 'coloredBlur')
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic')
      // 연결 렌더링
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', lineColor)
      .attr('stroke-width', (d) => d.value * 1.2)
      .attr('stroke-linecap', 'round')
//노드 그룹 렌더링 + 드래그
    const nodeGroup = g.append('g')
      .selectAll('g')
      .data(nodes)
      .enter()
      .append('g')
      .style('cursor', 'pointer')
      .call(
        d3.drag<any, any>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x; d.fy = d.y //현재 위치로 고정
          })
          .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })//마우스 따라 오기
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null; d.fy = null //고정 해제 -> 다시 시뮬레이션에 맡기기
          })
      )

    // 작은 점 노드 
    nodeGroup.append('circle')
      .attr('r', (d) => d.size * 1.0)  // 0.4 → 0.8
      .attr('fill', (d) => getGroupColor(d.group))
      .attr('fill-opacity', 0.4)
      .attr('stroke', (d) => getGroupColor(d.group))
      .attr('stroke-width', 1.5)

    // 텍스트 (기본엔 희미하게)
    nodeGroup.append('text')
      .text((d) => d.label)
      .attr('text-anchor', 'middle')
      .attr('dy', (d) => d.size * 0.8 + 12)
      .attr('font-size', '0px')        // 기본엔 안보이게
      .attr('fill', textColor)
      .attr('pointer-events', 'none')

    // 호버 이벤트
    nodeGroup
      .on('mouseover', function(_, d: any) {
        const connectedIds = new Set<string>()
        links.forEach(l => {
          const src = typeof l.source === 'string' ? l.source : (l.source as any).id
          const tgt = typeof l.target === 'string' ? l.target : (l.target as any).id
          if (src === d.id) connectedIds.add(tgt)
          if (tgt === d.id) connectedIds.add(src)
        })

        // 노드 강조 (선택 노드 크게 + 연결 노드 중간 + 나머지 흐리게)
        nodeGroup.selectAll('circle')
          .attr('fill', (n: any) => {
            if (n.id === d.id) return getGroupColor(n.group)
            if (connectedIds.has(n.id)) return getGroupColor(n.group)
            return isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'
          })
          .attr('r', (n: any) => {
            if (n.id === d.id) return n.size * 2.0
            if (connectedIds.has(n.id)) return n.size * 1.4
            return n.size * 0.4
          })
          .attr('filter', (n: any) => n.id === d.id ? 'url(#glow)' : 'none')

        // 텍스트 강조
        nodeGroup.selectAll('text')
          .attr('fill', (n: any) => {
          if (n.id === d.id || connectedIds.has(n.id)) return textHoverColor
          return 'rgba(0,0,0,0)'  // 나머지는 완전 투명
        })
        .attr('font-size', (n: any) => n.id === d.id ? '12px' : '10px')
        .attr('font-weight', (n: any) => n.id === d.id ? '600' : '400')

        // 연결선 강조
        link
          .attr('stroke', (l: any) => {
            const src = typeof l.source === 'string' ? l.source : l.source.id
            const tgt = typeof l.target === 'string' ? l.target : l.target.id
            if (src === d.id || tgt === d.id) return getGroupColor(d.group)
            return isDark ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)'
          })
          .attr('stroke-width', (l: any) => {
            const src = typeof l.source === 'string' ? l.source : l.source.id
            const tgt = typeof l.target === 'string' ? l.target : l.target.id
            return src === d.id || tgt === d.id ? l.value * 2 : l.value * 1.2
          })
      })

      //호버 아웃 : 모든 노드/선 원래 상태로 복원
      .on('mouseout', function() {
        nodeGroup.selectAll('circle')
        .attr('fill', (n: any) => getGroupColor(n.group))
        .attr('fill-opacity', 0.3)
        .attr('filter', 'none')
        .attr('r', (n: any) => n.size * 1.0)

        nodeGroup.selectAll('text')
          .attr('fill', 'rgba(0,0,0,0)')
        .attr('font-size', '0px')
          link
            .attr('stroke', lineColor)
            .attr('stroke-width', (d: any) => d.value * 1.2)
        })
        //노드 클릭 시 상위로 선택된 id 전달
      .on('click', (_, d: any) => onSelect(d.id))

      //매 프레임마다 위치 업데이트
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y)
      nodeGroup.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
    })

    return () => {simulation.stop()}
  }, [isDark])

  return null
}