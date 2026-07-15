import { useState, useEffect, useRef } from 'react'
import * as d3 from 'd3'
import GraphCanvas from '../components/Graph/GraphCanvas'
import SelectedDocument from '../components/Graph/SelectedDocument'
import DocumentList from '../components/Graph/DocumentList'

const BASE_URL = import.meta.env.VITE_API_URL

// 그룹은 진짜 임베딩 유사도 전까지 "확장자" 기준 임시 분류
// 승주의 임베딩/유사도 API 들어오면 이 부분을 진짜 유사도 그룹으로 교체
const extGroup: Record<string, number> = { PDF: 1, DOCX: 2, TXT: 3 }
const colorPalette = ['#7c6af7', '#4caf82', '#e8a838', '#94a3b8'] // PDF, DOCX, TXT, 기타
const getGroupColor = (group: number) => colorPalette[(group - 1) % colorPalette.length]
const groupLabels: Record<number, string> = { 1: 'PDF', 2: 'DOCX', 3: 'TXT', 4: '기타' }

const getExt = (filename: string) => filename.split('.').pop()?.toUpperCase() ?? ''

// 공백/한글 인코딩(NFC·NFD) 차이로 같은 이름이 다르게 비교되는 문제 방지
const normalizeFilename = (filename: string) => filename.trim().normalize('NFC')

interface DocumentItem {
  document_id: string
  filename: string
  room_id: string
  type: string
  created_at: string
}

interface Node { id: string; label: string; group: number; size: number }
interface Link { source: string; target: string; value: number }

interface GraphProps {
  onGoToAnalysis: (documentId: string) => void
}

export default function Graph({ onGoToAnalysis }: GraphProps) {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)
  const [isDark, setIsDark] = useState(false)
  const [zoomLevel, setZoomLevel] = useState(1)
  const [showPanel, setShowPanel] = useState(false)
  const svgRef = useRef<SVGSVGElement>(null)
  const zoomRef = useRef<any>(null)

  useEffect(() => {
    fetch(`${BASE_URL}/api/documents`)
      .then(r => r.json())
      .then(data => {
        const docs = (data.documents ?? []).filter((d: DocumentItem) => d.type === 'document')
        // 같은 파일명 중복 제거 — trim + NFC 정규화로 공백/한글 인코딩 차이까지 같은 이름으로 인식
        const unique = docs.filter((d: DocumentItem, i: number, self: DocumentItem[]) =>
          i === self.findIndex(x => normalizeFilename(x.filename) === normalizeFilename(d.filename))
        )
        setDocuments(unique)
      })
      .catch(err => console.error('그래프용 문서 목록 불러오기 실패:', err))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains('dark'))
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    setIsDark(document.documentElement.classList.contains('dark'))
    return () => observer.disconnect()
  }, [])

  // 문서 → 그래프 노드로 변환 (확장자 기준 임시 그룹)
  const nodes: Node[] = documents.map((doc) => ({
    id: doc.document_id,
    label: doc.filename,
    group: extGroup[getExt(doc.filename)] ?? 4,
    size: 6,
  }))

  // 연결선: 진짜 유사도 API 들어오기 전까지, 같은 room_id(같은 채팅방에서 업로드된 문서)끼리 임시로 연결
  // TODO: 승주 임베딩 유사도 API 연동되면 이 로직을 실제 유사도 기반 연결로 교체
  const links: Link[] = []
  const byRoom: Record<string, string[]> = {}
  documents.forEach((doc) => {
    if (!doc.room_id) return
    if (!byRoom[doc.room_id]) byRoom[doc.room_id] = []
    byRoom[doc.room_id].push(doc.document_id)
  })
  Object.values(byRoom).forEach((ids) => {
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        links.push({ source: ids[i], target: ids[j], value: 1 })
      }
    }
  })

  const connectedIds = links
    .filter(l => l.source === selected || l.target === selected)
    .map(l => l.source === selected ? l.target : l.source)

  const selectedDoc = documents.find(d => d.document_id === selected) ?? null
  const connectedDocs = documents.filter(d => connectedIds.includes(d.document_id))

  const handleSelect = (id: string) => {
    if (id === '') {
      setSelected(null)
      setShowPanel(false)
    } else {
      setSelected(id)
      setShowPanel(true)
    }
  }

  return (
    <div className="relative" style={{ height: 'calc(100vh - 48px)' }}>

      {/* 그래프 전체 화면 */}
      <div className="absolute inset-0 rounded-xl overflow-hidden border border-gray-100 dark:border-gray-800 bg-white dark:bg-[#0d0d0d]">
        <svg ref={svgRef} width="100%" height="100%" />
        {!loading && (
          <GraphCanvas
            nodes={nodes}
            links={links}
            isDark={isDark}
            getGroupColor={getGroupColor}
            onSelect={handleSelect}
            onZoomChange={setZoomLevel}
            zoomRef={zoomRef}
            svgRef={svgRef}
          />
        )}
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <p className="text-sm text-gray-400">그래프 불러오는 중...</p>
          </div>
        )}
      </div>

      {/* 좌측 상단 타이틀 */}
      <div className="absolute top-4 left-4 z-10">
        <h1 className="text-sm font-semibold text-gray-700 dark:text-white">그래프 시각화</h1>
        <p className="text-xs text-gray-400 mt-0.5">문서 유형 · 업로드 맥락 기반 연관성 시각화 (임시)</p>
      </div>

      {/* 우측 상단 줌 버튼 + 패널 토글 */}
      <div className="absolute top-4 right-4 z-10 flex flex-col gap-1.5">
        <button
          onClick={() => setShowPanel(!showPanel)}
          className={`w-8 h-8 rounded-lg flex items-center justify-center border shadow-sm transition ${
            showPanel
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50'
          }`}
          title="문서 목록"
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <line x1="3" y1="6" x2="21" y2="6" strokeLinecap="round"/>
            <line x1="3" y1="12" x2="21" y2="12" strokeLinecap="round"/>
            <line x1="3" y1="18" x2="21" y2="18" strokeLinecap="round"/>
          </svg>
        </button>
        <button
          onClick={() => { if(zoomRef.current && svgRef.current) d3.select(svgRef.current).transition().call(zoomRef.current.scaleBy, 1.3) }}
          className="w-8 h-8 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg flex items-center justify-center text-gray-600 dark:text-gray-300 hover:bg-gray-50 text-sm font-bold shadow-sm"
        >+</button>
        <div className="w-8 h-6 flex items-center justify-center text-xs text-gray-400 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          {Math.round(zoomLevel * 100)}%
        </div>
        <button
          onClick={() => { if(zoomRef.current && svgRef.current) d3.select(svgRef.current).transition().call(zoomRef.current.scaleBy, 0.7) }}
          className="w-8 h-8 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg flex items-center justify-center text-gray-600 dark:text-gray-300 hover:bg-gray-50 text-sm font-bold shadow-sm"
        >−</button>
        <button
          onClick={() => { if(zoomRef.current && svgRef.current) d3.select(svgRef.current).transition().call(zoomRef.current.transform, d3.zoomIdentity) }}
          className="w-8 h-8 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-50 text-xs shadow-sm"
        >↺</button>
      </div>

      {/* 범례 좌측 하단 */}
      <div className="absolute bottom-4 left-4 z-10 flex gap-3 bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm px-3 py-2 rounded-lg border border-gray-100 dark:border-gray-700">
        {Object.entries(groupLabels).map(([key, label]) => (
          <div key={key} className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full" style={{ background: getGroupColor(Number(key)) }} />
            <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
          </div>
        ))}
      </div>

      {/* 사이드 패널 */}
      {showPanel && (
        <div className="absolute top-4 right-16 z-10 flex flex-col gap-3 w-56">
          <div className="flex justify-end">
            <button
              onClick={() => { setShowPanel(false); setSelected(null) }}
              className="w-6 h-6 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-600 text-xs"
            >✕</button>
          </div>
          <DocumentList
            nodes={nodes}
            selected={selected}
            onSelect={handleSelect}
            getGroupColor={getGroupColor}
          />
          {selectedDoc && (
            <SelectedDocument
              doc={selectedDoc}
              connectedDocs={connectedDocs}
              onGoToAnalysis={() => onGoToAnalysis(selectedDoc.document_id)}
            />
          )}
        </div>
      )}
    </div>
  )
}